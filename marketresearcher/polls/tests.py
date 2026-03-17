import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from .models import (
    User,
    Survey,
    Question,
    AnswerOption,
    SurveyProgress,
    Answer,
)


@pytest.mark.django_db
def test_next_question_full_flow():
    client = APIClient()

    user = User.objects.create_user(username="test", password="123")
    client.force_authenticate(user=user)

    survey = Survey.objects.create(title="Survey", author=user)

    q1 = Question.objects.create(survey=survey, text="Q1", order=1)
    q2 = Question.objects.create(survey=survey, text="Q2", order=2)

    AnswerOption.objects.create(question=q1, text="A1", order=1)
    AnswerOption.objects.create(question=q2, text="A2", order=1)

    url = reverse("next-question", args=[survey.id])

    # --- 1. Первый запрос → первый вопрос
    res = client.get(url)
    assert res.status_code == 200
    assert res.data["id"] == q1.id

    # --- 2. Идемпотентность (без ответа тот же вопрос)
    res = client.get(url)
    assert res.status_code == 200
    assert res.data["id"] == q1.id

    # --- 3. Отвечаем на первый вопрос
    progress = SurveyProgress.objects.get(user=user, survey=survey)

    Answer.objects.create(
        progress=progress,
        question=q1,
    )

    # --- 4. Теперь должен прийти второй вопрос
    res = client.get(url)
    assert res.status_code == 200
    assert res.data["id"] == q2.id

    # --- 5. Отвечаем на второй вопрос
    Answer.objects.create(
        progress=progress,
        question=q2,
    )

    # --- 6. Опрос завершён
    res = client.get(url)
    assert res.status_code == 200
    assert res.data["detail"] == "Survey completed"

    # --- 7. Проверяем, что progress завершён
    progress.refresh_from_db()
    assert progress.finished_at is not None


@pytest.mark.django_db
def test_new_question_inserted_in_middle():
    client = APIClient()

    user = User.objects.create_user(username="test", password="123")
    client.force_authenticate(user=user)

    survey = Survey.objects.create(title="Survey", author=user)

    q1 = Question.objects.create(survey=survey, text="Q1", order=1)
    q3 = Question.objects.create(survey=survey, text="Q3", order=3)

    AnswerOption.objects.create(question=q1, text="A1", order=1)
    AnswerOption.objects.create(question=q3, text="A3", order=1)

    url = reverse("next-question", args=[survey.id])

    # ответили на первый вопрос
    res = client.get(url)
    progress = SurveyProgress.objects.get(user=user, survey=survey)

    Answer.objects.create(progress=progress, question=q1)

    # добавляем новый вопрос в середину
    q2 = Question.objects.create(survey=survey, text="Q2", order=2)
    AnswerOption.objects.create(question=q2, text="A2", order=1)

    # должен вернуться именно q2, а не q3
    res = client.get(url)

    assert res.status_code == 200
    assert res.data["id"] == q2.id