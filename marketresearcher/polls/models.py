from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import JSONField, Count, F, ExpressionWrapper, DurationField, Avg
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


class User(AbstractUser):
    is_survey_creator = models.BooleanField(default=False)


class Survey(models.Model):
    title = models.CharField(max_length=255)
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_surveys"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["author"]),
        ]

    def __str__(self):
        return self.title


class Question(models.Model):
    survey = models.ForeignKey(
        Survey,
        on_delete=models.CASCADE,
        related_name="questions"
    )
    text = models.TextField()
    order = models.PositiveIntegerField()
    allow_custom_answer = models.BooleanField(default=True)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["survey", "order"],
                name="unique_question_order"
            )
        ]
        indexes = [
            models.Index(fields=["survey", "order"]),
        ]

    def __str__(self):
        return f"{self.survey_id}: {self.text}"


class AnswerOption(models.Model):
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name="options"
    )
    text = models.CharField(max_length=255)
    order = models.PositiveIntegerField()

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["question", "order"],
                name="unique_option_order"
            )
        ]
        indexes = [
            models.Index(fields=["question", "order"]),
        ]

    def __str__(self):
        return self.text


class SurveyProgress(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'survey'],
                name='unique_user_survey'
            )
        ]
        indexes = [
            models.Index(fields=["user", "survey"]),
        ]

    def __str__(self):
        return f"{self.user_id} -> {self.survey_id}"


class Answer(models.Model):
    progress = models.ForeignKey(
        SurveyProgress,
        on_delete=models.CASCADE,
        related_name="answers"
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE
    )
    option = models.ForeignKey(
        AnswerOption,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    custom_answer = models.TextField(null=True, blank=True)
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['progress', 'question'],
                name='unique_answer_per_question'
            )
        ]
        indexes = [
            models.Index(fields=["progress", "question"]),
            models.Index(fields=["progress"]),
            models.Index(fields=["question"]),
        ]

    def clean(self):
        if not self.option and not self.custom_answer:
            raise ValidationError("Answer must have option or custom_answer")

        if self.option and self.custom_answer:
            raise ValidationError("Only one allowed")

        if self.option and self.option.question_id != self.question_id:
            raise ValidationError("Option does not belong to question")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class QuestionStatistics(models.Model):
    question = models.OneToOneField(
        Question,
        on_delete=models.CASCADE,
        related_name="statistics"
    )
    total_answers = models.BigIntegerField(default=0)
    option_counts = JSONField(default=dict, blank=True)
    custom_answers = JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Stats for question {self.question_id}"

    def recalc(self):
        answers = Answer.objects.filter(question=self.question)
        self.total_answers = answers.count()

        # Подсчет ответов по вариантам
        option_counts = (
            answers
            .exclude(option__isnull=True)
            .values('option_id')
            .annotate(count=Count('id'))
        )
        self.option_counts = {str(item['option_id']): item['count'] for item in option_counts}

        # Кастомные ответы
        self.custom_answers = list(
            answers
            .exclude(custom_answer__isnull=True)
            .values_list('custom_answer', flat=True)
        )

        self.save()


class SurveyStatistics(models.Model):
    survey = models.OneToOneField(
        Survey,
        on_delete=models.CASCADE,
        related_name="statistics"
    )
    total_answers = models.BigIntegerField(default=0)
    completed_attempts = models.BigIntegerField(default=0)
    average_time_seconds = models.FloatField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Survey stats {self.survey_id}"

    def recalc(self):
        progresses = SurveyProgress.objects.filter(
            survey=self.survey,
            finished_at__isnull=False
        ).annotate(
            time_spent=ExpressionWrapper(
                F('finished_at') - F('started_at'),
                output_field=DurationField()
            )
        )

        self.completed_attempts = progresses.count()
        self.average_time_seconds = (
            progresses.aggregate(avg=Avg('time_spent'))['avg'].total_seconds()
            if progresses.exists() else 0
        )

        self.total_answers = Answer.objects.filter(question__survey=self.survey).count()
        self.save()


@receiver(post_save, sender=Answer)
def update_statistics_on_answer(sender, instance, **kwargs):
    # Обновление статистики вопроса
    q_stats, _ = QuestionStatistics.objects.get_or_create(question=instance.question)
    q_stats.recalc()

    # Обновление статистики опроса
    survey_stats, _ = SurveyStatistics.objects.get_or_create(survey=instance.question.survey)
    survey_stats.recalc()
