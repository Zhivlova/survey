from django.urls import path
from .views import NextQuestionView

urlpatterns = [
    path(
        "surveys/<int:survey_id>/next-question/",
        NextQuestionView.as_view(),
        name="next-question",
    ),
]
