from django.urls import include, path

urls = [
    path('/quiz', include('quiz.urls')),
]

