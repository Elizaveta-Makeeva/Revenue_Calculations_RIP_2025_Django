from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
import time
import math
import random
import requests
from concurrent import futures

executor = futures.ThreadPoolExecutor(max_workers=3)

def calculate_ema(values):
    """Реализация EMA расчета как в Go-бэкенде"""
    n = float(len(values))
    if n == 0:
        return 0

    alpha = 2 / (n + 1)
    ema = values[0]
    
    for i in range(1, len(values)):
        ema = alpha * values[i] + (1 - alpha) * ema

    pow_val = math.pow(10, 3)
    return round(ema * pow_val) / pow_val

def calculate_period_forecast(period_data):
    """Расчет прогноза для одного периода с задержкой 5-10 секунд"""
    try:
        # Случайная задержка от 5 до 10 секунд
        delay = random.randint(5, 10)
        print(f"Calculating forecast for period {period_data['period_id']}, delay: {delay}s")
        time.sleep(delay)
        
        previous_revenue = period_data.get('previous_revenue', '')
        period_id = period_data['period_id']
        application_id = period_data['application_id']
        
        # Парсим предыдущую выручку
        parts = previous_revenue.split(';')
        revenue_values = []
        for p in parts:
            cleaned = p.strip()
            if cleaned:
                try:
                    revenue_values.append(float(cleaned))
                except ValueError:
                    continue
        
        if not revenue_values:
            return {
                'period_id': period_id,
                'application_id': application_id,
                'previous_revenue': previous_revenue,
                'forecasted_revenue': 0.0,
                'status': 'error',
                'error': 'No valid revenue data'
            }
        
        # Рассчитываем EMA
        forecast = calculate_ema(revenue_values)
        
        # Случайный результат (70% успех)
        success = random.random() < 0.7
        
        return {
            'period_id': period_id,
            'application_id': application_id,
            'previous_revenue': previous_revenue,
            'forecasted_revenue': forecast if success else 0.0,
            'status': 'success' if success else 'failed',
            'revenue_values': revenue_values
        }
        
    except Exception as e:
        return {
            'period_id': period_data.get('period_id'),
            'application_id': period_data.get('application_id'),
            'status': 'error',
            'error': str(e),
            'forecasted_revenue': 0.0
        }

def send_results_to_go_backend(results_data):
    """Отправка результатов обратно в Go"""
    try:
        callback_url = "http://localhost:8081/api/forecast-results"
        response = requests.post(callback_url, json=results_data, timeout=30)
        print(f"Results sent to Go, status: {response.status_code}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error sending results: {e}")
        return False

def forecast_calculation_callback(task):
    """Колбэк после завершения расчета"""
    try:
        result = task.result()
        print(f"Calculation completed for {result['total_periods']} periods")
        
        # Отправляем результаты в Go
        send_results_to_go_backend(result)
        
    except Exception as e:
        print(f"Error in calculation callback: {e}")

def calculate_application_forecast_async(periods_data, token):
    """Асинхронный расчет прогноза для всех периодов заявки"""
    try:
        results = []
        
        # Запускаем расчет для каждого периода в отдельном потоке
        future_to_period = {
            executor.submit(calculate_period_forecast, period): period 
            for period in periods_data
        }
        
        # Собираем результаты
        for future in futures.as_completed(future_to_period):
            period_data = future_to_period[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as exc:
                results.append({
                    'period_id': period_data.get('period_id'),
                    'application_id': period_data.get('application_id'),
                    'status': 'error',
                    'error': str(exc),
                    'forecasted_revenue': 0.0
                })
        
        # Считаем общую статистику
        total_forecast = sum(item.get('forecasted_revenue', 0) for item in results)
        successful_calculations = sum(1 for item in results if item.get('status') == 'success')
        total_periods = len(results)
        
        return {
            'periods': results,
            'token': token,
            'total_periods': total_periods,
            'successful_calculations': successful_calculations,
            'total_forecasted_revenue': total_forecast
        }
        
    except Exception as e:
        return {
            'error': str(e),
            'token': token
        }

@api_view(['POST'])
def calculate_forecast(request):
    """
    Основной endpoint для получения данных о периодах от Go-бэкенда
    и расчета прогноза выручки
    """
    # Проверяем токен авторизации
    auth_token = request.headers.get('Authorization', '').replace('Bearer ', '')
    expected_token = settings.AUTH_TOKEN
    
    if auth_token != expected_token:
        return Response(
            {'error': 'Invalid authorization token'}, 
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    # Проверяем наличие обязательных полей
    if 'application_id' not in request.data:
        return Response(
            {'error': 'application_id is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if 'periods' not in request.data:
        return Response(
            {'error': 'periods array is required'}, 
            status=status.HTTP_400_BAD_REQUEST
        )
    
    application_id = request.data['application_id']
    periods_data = request.data['periods']
    token = request.data.get('token', auth_token)
    
    print(f"Received forecast calculation request for application {application_id} with {len(periods_data)} periods")
    
    # Добавляем application_id к каждому периоду
    for period in periods_data:
        period['application_id'] = application_id
    
    # Запускаем асинхронный расчет прогноза
    task = executor.submit(calculate_application_forecast_async, periods_data, token)
    task.add_done_callback(forecast_calculation_callback)
    
    # Немедленно возвращаем ответ Go-бэкенду
    return Response({
        'status': 'forecast_calculation_started',
        'application_id': application_id,
        'periods_count': len(periods_data),
        'message': 'Forecast calculation is being processed asynchronously (5-10 seconds per period)'
    }, status=status.HTTP_200_OK)

@api_view(['POST'])
def receive_forecast_results(request):
    """
    Endpoint для приема результатов расчета от Django (для тестирования)
    """
    print("Received forecast results:", request.data)
    return Response({
        'status': 'forecast_results_received',
        'message': 'Forecast results received successfully'
    }, status=status.HTTP_200_OK)