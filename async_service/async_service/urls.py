from django.contrib import admin
from django.urls import path
from calculator.views import calculate_forecast, receive_forecast_results

urlpatterns = [
    path('admin/', admin.site.urls),
    path('calculate-forecast/', calculate_forecast, name='calculate-forecast'),
    path('forecast-results/', receive_forecast_results, name='receive-forecast-results'),
]