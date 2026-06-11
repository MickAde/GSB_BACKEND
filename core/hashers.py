from django.contrib.auth.hashers import Argon2PasswordHasher


class GSBArgon2Hasher(Argon2PasswordHasher):
    """
    Argon2id with reduced memory footprint for development and modest hardware.

    Django's default Argon2PasswordHasher uses memory_cost=102400 (100 MB per
    hash operation). That causes argon2.exceptions.HashingError on machines
    with limited available RAM, breaking both login and password reset.

    32 MB (memory_cost=32768) is still well above the minimum recommendation
    and is safe for production use. Raise toward 65536 (64 MB) on a dedicated
    server with ample RAM.
    """
    time_cost    = 2
    memory_cost  = 32768   # 32 MB  (default is 102400 = 100 MB)
    parallelism  = 2
