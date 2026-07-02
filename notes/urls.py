from django.urls import path
from .views import (
    NoteUploadView,
    NoteBulkUploadView,
    NoteCombinedUploadView,
    NoteListView,
    NoteDetailView,
    NoteStatusView,
    NoteConfirmOCRView,
    NoteRetryOCRView,
    NoteUpdateView,
    NoteDeleteView,
    NoteReplaceView,
    SchoolNoteListView,
    SchoolNoteDetailView,
    NoteConformityListCreateView,
    NoteConformityDetailView,
    NoteConformityStatusView,
    ConformityTopicsView,
    NoteConformityBulkView,
)

urlpatterns = [
    # Upload
    path('upload/',          NoteUploadView.as_view(),          name='note-upload'),
    path('upload/bulk/',     NoteBulkUploadView.as_view(),      name='note-upload-bulk'),
    path('upload/combined/', NoteCombinedUploadView.as_view(),  name='note-upload-combined'),

    # Collection — own notes
    path('',             NoteListView.as_view(),        name='note-list'),

    # School-wide browse (teacher / admin)
    path('school/',           SchoolNoteListView.as_view(),   name='note-school-list'),
    path('school/<uuid:pk>/', SchoolNoteDetailView.as_view(), name='note-school-detail'),

    # Conformity reports
    path('conformity/',                        NoteConformityListCreateView.as_view(), name='note-conformity-list'),
    path('conformity/topics/',                 ConformityTopicsView.as_view(),         name='note-conformity-topics'),
    path('conformity/bulk/',                   NoteConformityBulkView.as_view(),       name='note-conformity-bulk'),
    path('conformity/<uuid:pk>/',              NoteConformityDetailView.as_view(),     name='note-conformity-detail'),
    path('conformity/<uuid:pk>/status/',       NoteConformityStatusView.as_view(),     name='note-conformity-status'),

    # Single note resource
    path('<uuid:pk>/',             NoteDetailView.as_view(),      name='note-detail'),
    path('<uuid:pk>/status/',      NoteStatusView.as_view(),      name='note-status'),
    path('<uuid:pk>/confirm-ocr/', NoteConfirmOCRView.as_view(),  name='note-confirm-ocr'),
    path('<uuid:pk>/retry-ocr/',   NoteRetryOCRView.as_view(),   name='note-retry-ocr'),
    path('<uuid:pk>/replace/',     NoteReplaceView.as_view(),     name='note-replace'),
    path('<uuid:pk>/update/',      NoteUpdateView.as_view(),      name='note-update'),
    path('<uuid:pk>/delete/',      NoteDeleteView.as_view(),      name='note-delete'),
]
