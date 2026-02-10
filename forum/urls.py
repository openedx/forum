"""
URLs for forum.
"""

from django.urls import include, path

from forum.views.bans import (
    BanDetailAPIView,
    BannedUsersAPIView,
    BanUserAPIView,
    UnbanUserAPIView,
)
from forum.views.commentables import CommentablesCountAPIView
from forum.views.comments import CommentsAPIView, CreateThreadCommentAPIView
from forum.views.flags import CommentFlagAPIView, ThreadFlagAPIView
from forum.views.pins import PinThreadAPIView, UnpinThreadAPIView
from forum.views.search import SearchThreadsView
from forum.views.subscriptions import (
    SubscriptionAPIView,
    ThreadSubscriptionAPIView,
    UserSubscriptionAPIView,
)
from forum.views.threads import CreateThreadAPIView, ThreadsAPIView, UserThreadsAPIView
from forum.views.users import (
    UserActiveThreadsAPIView,
    UserAPIView,
    UserCourseStatsAPIView,
    UserCreateAPIView,
    UserEditAPIView,
    UserReadAPIView,
    UserRetireAPIView,
)
from forum.views.votes import CommentVoteView, ThreadVoteView

api_patterns = [
    # thread votes APIs
    path(
        "threads/<str:thread_id>/votes",
        ThreadVoteView.as_view(),
        name="thread-vote",
    ),
    path(
        "comments/<str:comment_id>/votes",
        CommentVoteView.as_view(),
        name="comment-vote",
    ),
    # abuse comment/thread APIs
    path(
        "comments/<str:comment_id>/abuse_<str:action>",
        CommentFlagAPIView.as_view(),
        name="comment-flags-api",
    ),
    path(
        "threads/<str:thread_id>/abuse_<str:action>",
        ThreadFlagAPIView.as_view(),
        name="thread-flags-api",
    ),
    # pin/unpin thread APIs
    path("threads/<str:thread_id>/pin", PinThreadAPIView.as_view(), name="pin-thread"),
    path(
        "threads/<str:thread_id>/unpin",
        UnpinThreadAPIView.as_view(),
        name="unpin-thread",
    ),
    # comments API
    path(
        "comments/<str:comment_id>",
        CommentsAPIView.as_view(),
        name="comments-api",
    ),
    path(
        "threads/<str:thread_id>/comments",
        CreateThreadCommentAPIView.as_view(),
        name="create-parent-comment-api",
    ),
    # search threads API
    path(
        "search/threads",
        SearchThreadsView.as_view(),
        name="search-thread-api",
    ),
    # subscription APIs
    path(
        "users/<str:user_id>/subscriptions",
        SubscriptionAPIView.as_view(),
        name="subscriptions",
    ),
    path(
        "users/<str:user_id>/subscribed_threads",
        UserSubscriptionAPIView.as_view(),
        name="user-subscriptions",
    ),
    path(
        "threads/<str:thread_id>/subscriptions",
        ThreadSubscriptionAPIView.as_view(),
        name="thread-subscriptions",
    ),
    # threads API
    path(
        "course/threads",
        CreateThreadAPIView.as_view(),
        name="create-thread-api",
    ),
    path(
        "threads",
        UserThreadsAPIView.as_view(),
        name="user-threads-api",
    ),
    path(
        "threads/<str:thread_id>",
        ThreadsAPIView.as_view(),
        name="threads-api",
    ),
    # commentables API
    path(
        "commentables/<str:course_id>/counts",
        CommentablesCountAPIView.as_view(),
        name="commentables-count",
    ),
    path(
        "users",
        UserCreateAPIView.as_view(),
        name="create-user",
    ),
    # Ban/Unban user APIs
    path(
        "users/bans",
        BanUserAPIView.as_view(),
        name="ban-user",
    ),
    path(
        "users/bans/<int:ban_id>",
        BanDetailAPIView.as_view(),
        name="ban-detail",
    ),
    path(
        "users/bans/<int:ban_id>/unban",
        UnbanUserAPIView.as_view(),
        name="unban-user",
    ),
    path(
        "users/banned",
        BannedUsersAPIView.as_view(),
        name="banned-users-list",
    ),
    path(
        "users/<str:user_id>",
        UserAPIView.as_view(),
        name="get-user-detail",
    ),
    path(
        "users/<str:user_id>/replace_username",
        UserEditAPIView.as_view(),
        name="edit-user",
    ),
    path(
        "users/<str:user_id>/read",
        UserReadAPIView.as_view(),
        name="user-read",
    ),
    path(
        "users/<str:user_id>/active_threads",
        UserActiveThreadsAPIView.as_view(),
        name="user-active-threads",
    ),
    path(
        "users/<str:course_id>/stats",
        UserCourseStatsAPIView.as_view(),
        name="user-course-stats",
    ),
    path(
        "users/<str:course_id>/update_stats",
        UserCourseStatsAPIView.as_view(),
        name="user-course-stats-update",
    ),
    path(
        "users/<str:user_id>/retire",
        UserRetireAPIView.as_view(),
        name="user-retire",
    ),
]

urlpatterns = [
    # for backward compatibility with edx-platform
    path("api/v1/", include(api_patterns)),
    # for when we will migrate edx-platform to the v2/ prefix
    path("api/v2/", include(api_patterns)),
]
