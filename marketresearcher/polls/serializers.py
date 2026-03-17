from rest_framework import serializers
from .models import AnswerOption, Question


class AnswerOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnswerOption
        fields = ("id", "text", "order")


class QuestionSerializer(serializers.ModelSerializer):
    options = AnswerOptionSerializer(many=True)

    class Meta:
        model = Question
        fields = (
            "id",
            "text",
            "order",
            "allow_custom_answer",
            "options",
        )