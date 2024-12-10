from fastapi import FastAPI, Request, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from typing import Dict, List, Optional
import json
import random
import asyncio
from datetime import datetime
from collections import defaultdict
from coefficients import CoefficientsCalculator

app = FastAPI()
templates = Jinja2Templates(directory="templates")
security = HTTPBasic()

# Хардкод учетных данных для простоты
PLAYERS = {
    "player1": "password1",
    "player2": "password2",
    "admin": "adminpass"
}


# Состояние игры
class GameState:
    def __init__(self):
        self.current_match = 0
        self.match_results = []
        self.player_connections = {}
        self.spectator_connections = {}
        self.player_choices = {}
        self.betting_round = False
        self.game_started = False
        self.spectator_bets = defaultdict(lambda: {"balance": 5000, "current_bets": {}})
        self.coefficients = {"player1": 0, "player2": 0}
        self.total_pool = 0
        self.calculator = CoefficientsCalculator()  # Инициализируем калькулятор коэффициентов


game_state = GameState()

def get_current_user(request: Request, credentials: HTTPBasicCredentials = Depends(security)):
    username = credentials.username
    password = credentials.password

    if username not in PLAYERS or PLAYERS[username] != password:
        return templates.TemplateResponse(
            "spectator.html",
            {"request": request}
        )
    return username


@app.get("/", response_class=HTMLResponse)
async def root(request: Request, user: str = Depends(get_current_user)):
    if user == "admin":
        return templates.TemplateResponse(
            "admin.html",
            {"request": request, "game_state": game_state}
        )
    elif user in ["player1", "player2"]:
        return templates.TemplateResponse(
            "player.html",
            {"request": request, "player": user}
        )
    else:
        return templates.TemplateResponse(
            "spectator.html",
            {"request": request}
        )


@app.websocket("/ws/player/{player_id}")
async def websocket_player_endpoint(websocket: WebSocket, player_id: str):
    await websocket.accept()
    game_state.player_connections[player_id] = websocket

    # Отправляем начальное состояние
    await websocket.send_json({
        "type": "game_status",
        "started": game_state.game_started
    })

    try:
        while True:
            data = await websocket.receive_text()
            choice = json.loads(data)["choice"]
            game_state.player_choices[player_id] = choice

            # Если оба игрока сделали выбор
            if len(game_state.player_choices) == 2:
                result = determine_winner(
                    game_state.player_choices["player1"],
                    game_state.player_choices["player2"]
                )
                game_state.match_results.append(result)

                # Отправляем результат обоим игрокам
                for player, ws in game_state.player_connections.items():
                    await ws.send_json({
                        "type": "result",
                        "result": result,
                        "match_number": len(game_state.match_results)
                    })

                # Очищаем выборы для следующего раунда
                game_state.player_choices = {}

                # Если сыграно 3 матча, открываем ставки
                if len(game_state.match_results) == 3:
                    game_state.betting_round = True

                # Обновляем коэффициенты после каждой игры
                update_coefficients()

    except WebSocketDisconnect:
        del game_state.player_connections[player_id]


@app.websocket("/ws/admin")
async def websocket_admin_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            await websocket.send_json({
                "type": "update",
                "coefficients": game_state.coefficients,
                "match_results": game_state.match_results,
                "total_pool": game_state.total_pool,
                "spectator_bets": dict(game_state.spectator_bets),
                "betting_round": game_state.betting_round,
                "game_started": game_state.game_started
            })
            if data["type"] == "admin_command":
                if data["command"] == "start_game":
                    game_state.game_started = True
                    # Оповещаем всех игроков о начале игры
                    for player_ws in game_state.player_connections.values():
                        await player_ws.send_json({
                            "type": "game_status",
                            "started": True
                        })

                elif data["command"] == "stop_betting":
                    game_state.betting_round = False
                    # Оповещаем всех зрителей о закрытии ставок
                    for spectator_ws in game_state.spectator_connections.values():
                        await spectator_ws.send_json({
                            "type": "betting_status",
                            "enabled": False
                        })

                elif data["command"] == "start_betting":
                    game_state.betting_round = True
                    # Оповещаем всех зрителей об открытии ставок
                    for spectator_ws in game_state.spectator_connections.values():
                        await spectator_ws.send_json({
                            "type": "betting_status",
                            "enabled": True
                        })

                elif data["command"] == "show_results":
                    # Обработка результатов и начисление выигрышей
                    process_bets(game_state.match_results[-1]["winner"])
                    # Отправляем обновленные балансы всем зрителям
                    for spectator_id, spectator_ws in game_state.spectator_connections.items():
                        await spectator_ws.send_json({
                            "type": "balance_update",
                            "balance": game_state.spectator_bets[spectator_id]["balance"]
                        })

            # Отправляем обновление состояния админу
            websocket.send_json({
                "type": "update",
                "coefficients": game_state.coefficients,
                "match_results": game_state.match_results,
                "total_pool": game_state.total_pool,
                "spectator_bets": dict(game_state.spectator_bets),
                "betting_round": game_state.betting_round,
                "game_started": game_state.game_started
            })
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass


@app.websocket("/ws/spectator/{spectator_id}")
async def websocket_spectator_endpoint(websocket: WebSocket, spectator_id: str):
    await websocket.accept()
    game_state.spectator_connections[spectator_id] = websocket

    # Отправляем начальное состояние
    await websocket.send_json({
        "type": "initial_state",
        "balance": game_state.spectator_bets[spectator_id]["balance"],
        "coefficients": game_state.coefficients,
        "betting_enabled": game_state.betting_round
    })

    try:
        while True:
            data = await websocket.receive_json()

            if data["type"] == "bet":
                if game_state.betting_round:
                    player = data["player"]
                    amount = int(data["amount"])

                    # Проверяем, достаточно ли средств
                    if amount <= game_state.spectator_bets[spectator_id]["balance"]:
                        game_state.spectator_bets[spectator_id]["balance"] -= amount
                        game_state.spectator_bets[spectator_id]["current_bets"][player] = amount
                        game_state.total_pool += amount

                        await websocket.send_json({
                            "type": "bet_accepted",
                            "balance": game_state.spectator_bets[spectator_id]["balance"]
                        })
    except WebSocketDisconnect:
        del game_state.spectator_connections[spectator_id]


def determine_winner(choice1: str, choice2: str) -> dict:
    choices = {"rock": 0, "paper": 1, "scissors": 2}
    diff = (choices[choice1] - choices[choice2]) % 3

    if diff == 0:
        winner = "tie"
    elif diff == 1:
        winner = "player1"
    else:
        winner = "player2"

    return {
        "player1_choice": choice1,
        "player2_choice": choice2,
        "winner": winner
    }


def update_coefficients():
    # Добавляем последний результат в калькулятор
    if game_state.match_results:
        game_state.calculator.add_result(game_state.match_results[-1]["winner"])

    # Получаем новые коэффициенты
    game_state.coefficients = game_state.calculator.calculate_coefficients()

    # Оповещаем всех зрителей о новых коэффициентах
    for spectator_ws in game_state.spectator_connections.values():
        asyncio.create_task(spectator_ws.send_json({
            "type": "coefficients_update",
            "coefficients": game_state.coefficients
        }))


def process_bets(winner: str):
    for spectator_id, data in game_state.spectator_bets.items():
        total_winnings = 0
        for player, bet_amount in data["current_bets"].items():
            if player == winner:
                winnings = int(bet_amount * game_state.coefficients[player])
                total_winnings += winnings

        # Начисляем выигрыш и очищаем текущие ставки
        data["balance"] += total_winnings
        data["current_bets"] = {}