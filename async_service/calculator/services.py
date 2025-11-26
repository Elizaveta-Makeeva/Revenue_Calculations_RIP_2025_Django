import time
import math
import requests
from concurrent import futures
from django.conf import settings

executor = futures.ThreadPoolExecutor(max_workers=3)

def calculate_ema(values):
    """
    Реализация EMA расчета как в Go-бэкенде
    """
    n = float(len(values))
    if n == 0:
        return 0

    alpha = 2 / (n + 1)
    ema = values[0]
    
    for i in range(1, len(values)):
        ema = alpha * values[i] + (1 - alpha) * ema

    pow_val = math.pow(10, 3)
    return round(ema * pow_val) / pow_val

def parse_previous_revenue(previous_revenue_str):
    """
    Парсинг строки с предыдущей выручкой (формат: "1000;1500;2000")
    """
    try:
        parts = previous_revenue_str.split(';')
        values = []
        for p in parts:
            cleaned = p.strip()
            if cleaned:
                values.append(float(cleaned))
        return values
    except (ValueError, AttributeError):
        return []

def calculate_period_forecast(period_data):
    """
    Расчет прогноза для одного периода с задержкой 5-10 секунд
    """
    try:
        # Случайная задержка от 5 до 10 секунд
        delay = 5 + (hash(str(period_data)) % 6)  # 5-10 секунд
        time.sleep(delay)
        
        previous_revenue = period_data.get('previous_revenue', '')
        period_id = period_data.get('period_id')
        application_id = period_data.get('application_id')
        
        # Парсим предыдущую выручку
        revenue_values = parse_previous_revenue(previous_revenue)
        
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
        
        # Случайный результат успех/неуспех (70% успех)
        import random
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
            'previous_revenue': period_data.get('previous_revenue', ''),
            'forecasted_revenue': 0.0,
            'status': 'error',
            'error': str(e)
        }

def calculate_application_forecast_async(periods_data, token):
    """
    Асинхронный расчет прогноза для всех периодов заявки
    """
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

def send_forecast_results_to_go_backend(results_data):
    """
    Отправка результатов прогноза обратно на Go-бэкенд
    """
    try:
        callback_url = f"{settings.GO_BACKEND_URL}/api/forecast-results"
        
        response = requests.post(
            callback_url,
            json=results_data,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        
        return {
            'status_code': response.status_code,
            'response_text': response.text
        }
    except requests.exceptions.RequestException as e:
        print(f"Error sending results to Go backend: {e}")
        return {
            'error': f"Failed to send forecast results to Go backend: {str(e)}"
        }

def forecast_calculation_callback(task):
    """
    Колбэк для отправки результатов после завершения расчета прогноза
    """
    try:
        result = task.result()
        print(f"Calculation completed, sending results for {result.get('total_periods', 0)} periods")
    except futures._base.CancelledError:
        print("Calculation was cancelled")
        return
    
    # Отправляем результаты обратно на Go-бэкенд
    send_result = send_forecast_results_to_go_backend(result)
    print(f"Results sent to Go backend: {send_result}")