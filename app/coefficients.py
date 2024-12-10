from math import exp, factorial
from typing import Dict, List, Tuple


class CoefficientsCalculator:
    def __init__(self, margin: float = 0.05):
        """
        Инициализация калькулятора коэффициентов

        Args:
            margin: Маржа букмекера (по умолчанию 5%)
        """
        self.margin = margin
        self.historical_results = []

    def add_result(self, winner: str):
        """
        Добавление результата матча в историю

        Args:
            winner: Победитель матча ('player1' или 'player2')
        """
        self.historical_results.append(winner)

    def _calculate_poisson_probability(self, k: int, lambda_param: float) -> float:
        """
        Вычисление вероятности по распределению Пуассона

        Args:
            k: Количество успехов
            lambda_param: Параметр распределения Пуассона (ожидаемое количество успехов)

        Returns:
            Вероятность получить ровно k успехов
        """
        return (lambda_param ** k * exp(-lambda_param)) / factorial(k)

    def _calculate_win_rates(self) -> Tuple[float, float]:
        """
        Рассчитывает частоту побед каждого игрока

        Returns:
            Кортеж с частотой побед первого и второго игрока
        """
        if not self.historical_results:
            return 0.5, 0.5

        total_games = len(self.historical_results)
        p1_wins = sum(1 for result in self.historical_results if result == 'player1')
        p2_wins = sum(1 for result in self.historical_results if result == 'player2')

        # Используем сглаживание Лапласа для избежания нулевых вероятностей
        p1_rate = (p1_wins + 1) / (total_games + 2)
        p2_rate = (p2_wins + 1) / (total_games + 2)

        return p1_rate, p2_rate

    def calculate_coefficients(self) -> Dict[str, float]:
        """
        Рассчитывает коэффициенты ставок на основе исторических данных

        Returns:
            Словарь с коэффициентами для каждого игрока
        """
        p1_rate, p2_rate = self._calculate_win_rates()

        # Рассчитываем параметр лямбда для распределения Пуассона
        # Используем исторические данные за последние 5 матчей
        recent_games = self.historical_results[-5:] if len(self.historical_results) > 5 else self.historical_results

        # Лямбда - это среднее количество побед за период
        lambda_p1 = p1_rate * len(recent_games)
        lambda_p2 = p2_rate * len(recent_games)

        # Вычисляем вероятности побед через распределение Пуассона
        p1_poisson_prob = self._calculate_poisson_probability(1, lambda_p1)
        p2_poisson_prob = self._calculate_poisson_probability(1, lambda_p2)

        # Нормализуем вероятности, чтобы их сумма была равна 1
        total_prob = p1_poisson_prob + p2_poisson_prob
        p1_prob = p1_poisson_prob / total_prob
        p2_prob = p2_poisson_prob / total_prob

        # Добавляем маржу букмекера
        margin_multiplier = 1 - self.margin

        # Рассчитываем коэффициенты
        # Коэффициент = 1 / (вероятность * (1 - маржа))
        coef_p1 = round(1 / (p1_prob * margin_multiplier), 2)
        coef_p2 = round(1 / (p2_prob * margin_multiplier), 2)

        return {
            'player1': coef_p1,
            'player2': coef_p2
        }