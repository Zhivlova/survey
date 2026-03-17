from django.db.models import OuterRef, Exists
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Survey, SurveyProgress, Question, Answer
from .serializers import QuestionSerializer


class NextQuestionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, survey_id):
        user = request.user

        survey = get_object_or_404(
            Survey.objects.select_related("author"),
            id=survey_id
        )

        progress, _ = SurveyProgress.objects.get_or_create(
            user=user,
            survey=survey,
        )

        if progress.finished_at:
            return Response({"detail": "Survey already completed"}, status=400)

        # есть ли ответ на этот вопрос
        answered_subquery = Answer.objects.filter(
            progress=progress,
            question=OuterRef("pk"),
        )

        # берём первый не отвеченный вопрос
        next_question = (
            Question.objects
            .filter(survey=survey)
            .annotate(answered=Exists(answered_subquery))
            .filter(answered=False)
            .prefetch_related("options")
            .order_by("order")
            .first()
        )

        if not next_question:
            progress.finished_at = timezone.now()
            progress.save(update_fields=["finished_at"])

            return Response({"detail": "Survey completed"})

        serializer = QuestionSerializer(next_question)
        return Response(serializer.data)