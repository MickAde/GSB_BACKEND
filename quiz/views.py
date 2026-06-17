import logging
from decimal import Decimal
from django.db import transaction
from django.db.models import Avg, Count, Max, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as drf_serializers
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAnyAdmin, IsStudent, IsTeacher, IsVisitor
from .models import Quiz, QuizAttempt, QuizAttemptAnswer, QuizQuestion, QuizStatus
from .serializers import (
    AttemptResultSerializer,
    CreateQuizSerializer,
    QuizDetailSerializer,
    QuizListSerializer,
    QuizStatusSerializer,
    SubmitAttemptSerializer,
)

logger = logging.getLogger(__name__)


def _dispatch_quiz_task(quiz_id: str):
    from .tasks import generate_quiz_questions
    from django.conf import settings
    if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False):
        # In dev (eager mode), run synchronously but isolate exceptions so the
        # 202 response is always returned. The task sets FAILED status itself.
        try:
            generate_quiz_questions.apply(args=[str(quiz_id)])
        except Exception:
            logger.exception('Eager quiz task raised for quiz %s', quiz_id)
            Quiz.unscoped.filter(pk=quiz_id).update(
                status='FAILED',
                error_message='Quiz generation failed (dev eager mode).',
            )
    else:
        task = generate_quiz_questions.apply_async(args=[str(quiz_id)])
        Quiz.unscoped.filter(pk=quiz_id).update(ai_task_id=task.id)


class CreateQuizView(APIView):
    """POST /api/v1/quiz/ — generate a quiz from a READY note."""

    def get_permissions(self):
        return [(IsStudent | IsVisitor)()]

    @extend_schema(request=CreateQuizSerializer, responses={202: QuizListSerializer})
    def post(self, request):
        ser = CreateQuizSerializer(data=request.data, context={'request': request})
        ser.is_valid(raise_exception=True)

        note = ser.context['note']
        quiz = Quiz.objects.create(
            owner=request.user,
            school=request.user.school,
            note=note,
            title=f'Quiz: {note.file_name}',
            difficulty=ser.validated_data['difficulty'],
            num_questions=ser.validated_data['num_questions'],
            status=QuizStatus.GENERATING,
        )

        transaction.on_commit(lambda: _dispatch_quiz_task(str(quiz.id)))

        return Response(
            {'quiz_id': str(quiz.id), 'status': quiz.status},
            status=status.HTTP_202_ACCEPTED,
        )


class ListQuizzesView(APIView):
    """GET /api/v1/quiz/ — list the current student's quizzes."""

    def get_permissions(self):
        return [(IsStudent | IsVisitor)()]

    @extend_schema(responses={200: QuizListSerializer(many=True)})
    def get(self, request):
        quizzes = Quiz.objects.filter(owner=request.user).select_related('note')
        return Response(QuizListSerializer(quizzes, many=True).data)


class QuizDetailView(APIView):
    """GET /api/v1/quiz/<id>/ — quiz detail with questions (READY only)."""

    def get_permissions(self):
        return [(IsStudent | IsVisitor)()]

    @extend_schema(responses={200: QuizDetailSerializer})
    def get(self, request, pk):
        try:
            quiz = Quiz.objects.select_related('note').get(pk=pk, owner=request.user)
        except Quiz.DoesNotExist:
            return Response({'detail': 'Quiz not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(QuizDetailSerializer(quiz).data)


class QuizStatusView(APIView):
    """GET /api/v1/quiz/<id>/status/ — lightweight status poll."""

    def get_permissions(self):
        return [(IsStudent | IsVisitor)()]

    @extend_schema(responses={200: QuizStatusSerializer})
    def get(self, request, pk):
        try:
            quiz = Quiz.objects.get(pk=pk, owner=request.user)
        except Quiz.DoesNotExist:
            return Response({'detail': 'Quiz not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(QuizStatusSerializer(quiz).data)


class SubmitAttemptView(APIView):
    """POST /api/v1/quiz/<id>/attempt/ — submit answers and receive graded results."""

    def get_permissions(self):
        return [(IsStudent | IsVisitor)()]

    @extend_schema(request=SubmitAttemptSerializer, responses={201: AttemptResultSerializer})
    def post(self, request, pk):
        try:
            quiz = Quiz.objects.prefetch_related('questions').get(pk=pk, owner=request.user)
        except Quiz.DoesNotExist:
            return Response({'detail': 'Quiz not found.'}, status=status.HTTP_404_NOT_FOUND)

        if quiz.status != QuizStatus.READY:
            return Response(
                {'detail': 'Quiz is not ready yet.'},
                status=status.HTTP_409_CONFLICT,
            )

        ser = SubmitAttemptSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        answers_data = ser.validated_data['answers']
        time_taken   = ser.validated_data.get('time_taken_s')

        question_map = {str(q.id): q for q in quiz.questions.all()}
        score = 0
        answer_records = []

        for ans in answers_data:
            q_id   = str(ans['question_id'])
            chosen = (ans.get('chosen') or '').upper()[:1]
            q_obj  = question_map.get(q_id)
            if not q_obj:
                continue
            correct = chosen == q_obj.correct
            if correct:
                score += 1
            answer_records.append(QuizAttemptAnswer(
                question=q_obj,
                chosen=chosen,
                is_correct=correct,
            ))

        total      = len(answer_records)
        percentage = Decimal(score / total * 100).quantize(Decimal('0.01')) if total else Decimal('0.00')

        with transaction.atomic():
            attempt = QuizAttempt.objects.create(
                quiz=quiz,
                school=request.user.school,
                student=request.user,
                score=score,
                total=total,
                percentage=percentage,
                time_taken_s=time_taken,
            )
            for ar in answer_records:
                ar.attempt = attempt
            QuizAttemptAnswer.objects.bulk_create(answer_records)

        attempt_with_answers = QuizAttempt.objects.prefetch_related(
            'answers__question'
        ).get(pk=attempt.pk)
        return Response(AttemptResultSerializer(attempt_with_answers).data, status=status.HTTP_201_CREATED)


class AttemptResultView(APIView):
    """GET /api/v1/quiz/<id>/attempt/ — retrieve the most recent attempt."""

    def get_permissions(self):
        return [(IsStudent | IsVisitor)()]

    @extend_schema(responses={200: AttemptResultSerializer})
    def get(self, request, pk):
        try:
            quiz = Quiz.objects.get(pk=pk, owner=request.user)
        except Quiz.DoesNotExist:
            return Response({'detail': 'Quiz not found.'}, status=status.HTTP_404_NOT_FOUND)

        attempt = (
            QuizAttempt.objects
            .filter(quiz=quiz, student=request.user)
            .prefetch_related('answers__question')
            .order_by('-completed_at')
            .first()
        )
        if not attempt:
            return Response({'detail': 'No attempt found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(AttemptResultSerializer(attempt).data)


class PerformanceStatsView(APIView):
    """GET /api/v1/quiz/performance/ — aggregate student performance stats."""

    def get_permissions(self):
        return [(IsStudent | IsVisitor)()]

    def get(self, request):
        attempts = QuizAttempt.objects.filter(student=request.user).select_related('quiz__note')

        total_attempts  = attempts.count()
        overall_average = float(attempts.aggregate(avg=Avg('percentage'))['avg'] or 0)

        # Readiness score: weighted avg over last 10 attempts
        # difficult × 1.5, moderate × 1.0, easy × 0.7
        WEIGHTS = {'difficult': 1.5, 'moderate': 1.0, 'easy': 0.7}
        last_10 = list(attempts.order_by('-completed_at')[:10])
        if last_10:
            weighted_sum = sum(float(a.percentage) * WEIGHTS.get(a.quiz.difficulty, 1.0) for a in last_10)
            weight_total = sum(WEIGHTS.get(a.quiz.difficulty, 1.0) for a in last_10)
            readiness_score = round(weighted_sum / weight_total, 1) if weight_total else 0.0
        else:
            readiness_score = 0.0

        # Study streak: consecutive days with at least one attempt
        streak = 0
        if total_attempts:
            today = timezone.now().date()
            check_date = today
            while True:
                if attempts.filter(
                    completed_at__date=check_date
                ).exists():
                    streak += 1
                    check_date -= timezone.timedelta(days=1)
                else:
                    break

        # Subject breakdown
        subject_data = {}
        for a in attempts:
            subj = a.quiz.note.subject or 'General'
            if subj not in subject_data:
                subject_data[subj] = {'subject': subj, 'attempts': 0, 'total_pct': 0.0}
            subject_data[subj]['attempts'] += 1
            subject_data[subj]['total_pct'] += float(a.percentage)
        subjects = [
            {
                'subject': v['subject'],
                'attempts': v['attempts'],
                'average': round(v['total_pct'] / v['attempts'], 1),
            }
            for v in subject_data.values()
        ]

        # Difficulty breakdown
        diff_data = {}
        for a in attempts:
            d = a.quiz.difficulty
            if d not in diff_data:
                diff_data[d] = {'attempts': 0, 'total_pct': 0.0}
            diff_data[d]['attempts'] += 1
            diff_data[d]['total_pct'] += float(a.percentage)
        difficulty_breakdown = {
            d: {
                'attempts': v['attempts'],
                'average': round(v['total_pct'] / v['attempts'], 1),
            }
            for d, v in diff_data.items()
        }

        # Recent attempts (last 5)
        recent = AttemptResultView  # reuse serializer
        from .serializers import AttemptResultSerializer
        recent_attempts_qs = (
            QuizAttempt.objects
            .filter(student=request.user)
            .select_related('quiz')
            .order_by('-completed_at')[:5]
        )
        recent_attempts = [
            {
                'id': str(a.id),
                'quiz_title': a.quiz.title,
                'difficulty': a.quiz.difficulty,
                'score': a.score,
                'total': a.total,
                'percentage': float(a.percentage),
                'completed_at': a.completed_at.isoformat(),
            }
            for a in recent_attempts_qs
        ]

        return Response({
            'total_attempts':        total_attempts,
            'overall_average':       round(overall_average, 1),
            'readiness_score':       readiness_score,
            'study_streak':          streak,
            'subjects':              subjects,
            'difficulty_breakdown':  difficulty_breakdown,
            'recent_attempts':       recent_attempts,
        })


class TeacherStudentStatsView(APIView):
    """GET /api/v1/teacher/students/ — all students with quiz performance stats."""

    def get_permissions(self):
        return [IsTeacher()]

    def get(self, request):
        from users.models import User, UserRole

        students = User.objects.filter(
            school=request.user.school,
            role=UserRole.STUDENT,
            is_active=True,
        ).order_by('last_name', 'first_name')

        results = []
        for student in students:
            attempts = QuizAttempt.unscoped.filter(student=student)
            agg      = attempts.aggregate(
                total=Count('id'),
                avg=Avg('percentage'),
                last=Max('completed_at'),
            )
            results.append({
                'id':            str(student.id),
                'full_name':     student.full_name,
                'username':      student.username or '',
                'total_attempts': agg['total'] or 0,
                'average_score':  round(float(agg['avg']), 1) if agg['avg'] is not None else None,
                'last_active':    agg['last'].isoformat() if agg['last'] else None,
            })

        return Response(results)
