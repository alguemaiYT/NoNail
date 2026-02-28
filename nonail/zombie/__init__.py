"""Zombie Mode — Master/Slave remote control system (BETA/Experimental)."""

ZOMBIE_ENABLED = False


def require_zombie():
    """Gate check — raise if zombie mode is not enabled."""
    if not ZOMBIE_ENABLED:
        raise RuntimeError(
            "Zombie Mode is an experimental feature.\n"
            "Enable it with: export NONAIL_ZOMBIE=1\n"
            "Or pass --experimental to the zombie command."
        )
