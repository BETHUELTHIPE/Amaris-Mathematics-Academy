from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .serializers import AssistantQuestionSerializer, AssistantResponseSerializer
from .services.amaris_assistant import AssistantUnavailable, ask_amaris_assistant


class AssistantThrottle(AnonRateThrottle):
    scope = "assistant"


class AmarisAssistantView(APIView):
    permission_classes = (AllowAny,)
    throttle_classes = (AssistantThrottle,)

    @extend_schema(
        request=AssistantQuestionSerializer,
        responses={200: AssistantResponseSerializer},
    )
    def post(self, request):
        serializer = AssistantQuestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            reply = ask_amaris_assistant(serializer.validated_data["question"])
        except AssistantUnavailable:
            return Response(
                {
                    "detail": (
                        "Amaris Assistant is temporarily unavailable. "
                        "Please use the Contact page for assistance."
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        response = AssistantResponseSerializer(
            {
                "assistant": "Amaris Assistant",
                "answer": reply.answer,
                "grounded_on": "published Amaris Mathematics Academy website content",
            }
        )
        return Response(response.data, status=status.HTTP_200_OK)
