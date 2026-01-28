"""
Native Python Commenttables APIs.
"""

from forum.backend import get_backend


def get_commentables_stats(course_id: str) -> dict[str, int]:
    """
    Get the threads count based on thread_type and group them by commentable_id.

    Parameters:
        course_id: The ID of the course.
    Body:
        Empty.
    Response:
        The threads count for the given course_id based on thread_type.
        e.g.
        response = {'course': {'discussion': 1, 'question': 1}}
    """
    backend = get_backend(course_id)()
    return backend.get_commentables_counts_based_on_type(course_id)
