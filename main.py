
from highrise import BaseBot, __main__, CurrencyItem, Item, Position, AnchorPosition, SessionMetadata, User
from highrise.__main__ import BotDefinition
from asyncio import run as arun, Lock
from json import load, dump
import asyncio
import os
import aiofiles
from dataclasses import dataclass, asdict
from typing import Dict, Optional, Tuple, List
import json
import time

@dataclass
class GameState:
    board: List[List[str]]
    current_player: str
    game_active: bool
    conversation_id: str
    last_activity: float

class Bot(BaseBot):
    def __init__(self):
        super().__init__()
        self.games: Dict[str, GameState] = {}
        self.game_locks: Dict[str, Lock] = {}
        self.save_lock = Lock()
        self.save_path = "saved_games.json"
        self.me = "1_on_1:67b2e6322df65074dacc6bc0:67d16801c9b11edcbb96af0f"
        self.initialize_games()
        self.task = None  # تغيير طريقة تعريف المهمة

    async def on_start(self, session_metadata: SessionMetadata) -> None:
        """يتم استدعاؤها عند بدء تشغيل البوت"""
        self.task = asyncio.create_task(self.check_inactive_games())

    async def check_inactive_games(self):
        """التحقق دوريًا من الألعاب غير النشطة"""
        while True:
            try:
                await asyncio.sleep(30)
                current_time = time.time()
                for conv_id in list(self.games.keys()):
                    game = self.games.get(conv_id)
                    if game and game.game_active and (current_time - game.last_activity) > 120:
                        async with self.game_locks.get(conv_id, Lock()):
                            game.game_active = False
                            await self.save_games()
                            await self.highrise.send_message(conv_id, "⏰ تم إنهاء اللعبة بسبب عدم النشاط لأكثر من دقيقتين.")
            except Exception as e:
                print(f"Error in check_inactive_games: {str(e)}")

    def initialize_games(self):
        if os.path.exists(self.save_path):
            with open(self.save_path, "r") as f:
                saved_games = load(f) if os.path.getsize(self.save_path) > 0 else []
            for game_data in saved_games:
                game = GameState(
                    board=game_data["board"],
                    current_player=game_data["current_player"],
                    game_active=game_data["game_active"],
                    conversation_id=game_data["conversation_id"],
                    last_activity=game_data.get("last_activity", time.time())
                )
                self.games[game.conversation_id] = game
                self.game_locks[game.conversation_id] = Lock()

    # بقية الدوال تبقى كما هي بدون تغيير...

    async def save_games(self):
        async with self.save_lock:
            saved_games = [asdict(game) for game in self.games.values()]
            async with aiofiles.open(self.save_path, "w") as f:
                await f.write(json.dumps(saved_games))

    # ... (الوظائف المساعدة الأخرى تبقى كما هي)

    def num_to_coords(self, num: int) -> Tuple[int, int]:
        num -= 1
        return (num // 3, num % 3)

    def format_board(self, board: list) -> str:
        formatted = []
        for i, row in enumerate(board):
            line = []
            for j, cell in enumerate(row):
                display = cell if cell != " " else str(i*3 + j + 1)
                line.append(display)
            formatted.append(" | ".join(line))
        return "\n---------\n".join(formatted)

    def check_winner(self, board: list, player: str) -> bool:
        for i in range(3):
            if all(board[i][j] == player for j in range(3)): return True
            if all(board[j][i] == player for j in range(3)): return True
        if board[0][0] == board[1][1] == board[2][2] == player: return True
        if board[0][2] == board[1][1] == board[2][0] == player: return True
        return False
# ... (الاستيرادات الأخرى تبقى كما هي)

    async def minimax(self, board: list, is_maximizing: bool) -> int:
        if self.check_winner(board, "O"): return 1
        if self.check_winner(board, "X"): return -1
        if all(cell != " " for row in board for cell in row): return 0

        if is_maximizing:
            best = -float('inf')
            for i in range(3):
                for j in range(3):
                    if board[i][j] == " ":
                        board[i][j] = "O"
                        current_score = await self.minimax(board, False)  # أضيف await >
                        best = max(best, current_score)
                        board[i][j] = " "
            return best
        else:
            best = float('inf')
            for i in range(3):
                for j in range(3):
                    if board[i][j] == " ":
                        board[i][j] = "X"
                        current_score = await self.minimax(board, True)  # أضيف await ه>
                        best = min(best, current_score)
                        board[i][j] = " "
            return best

    async def ai_move(self, board: list) -> Tuple[int, int]:
        best_score = -float('inf')
        best_move = (0, 0)
        for i in range(3):
            for j in range(3):
                if board[i][j] == " ":
                    board[i][j] = "O"
                    score = await self.minimax(board, False)  # أضيف await هنا
                    board[i][j] = " "
                    if score > best_score:
                        best_score = score
                        best_move = (i, j)
        return best_move


    async def handle_game_logic(self, conversation_id: str, message: str) -> str:
        async with self.game_locks.get(conversation_id, Lock()):
            if conversation_id not in self.games:
                self.games[conversation_id] = GameState(
                    board=[[" " for _ in range(3)] for _ in range(3)],
                    current_player="X",
                    game_active=False,
                    conversation_id=conversation_id,
                    last_activity=time.time()
                )
                self.game_locks[conversation_id] = Lock()

            game = self.games[conversation_id]
            game.last_activity = time.time()  # تحديث وقت النشاط

            response: str = "❌ حدث خطأ غير متوقع. الرجاء إعادة المحاولة."

        # معالجة أمر الخروج
            if message.lower() == "exit":
                game.game_active = False
                await self.save_games()
                return "تم إيقاف اللعبة الحالية."

        # معالجة الحالة عندما اللعبة غير نشطة
            if not game.game_active:
                if message.lower() in ["start", "ابداء", "بداء", "ابدا"]:
                    game.board = [[" " for _ in range(3)] for _ in range(3)]
                    game.current_player = "X"
                    game.game_active = True
                    response = (
                        "🎮 بدأت لعبة جديدة!\n"
                        f"{self.format_board(game.board)}\n"
                        "اختر رقمًا بين 1-9:"
                    )
                else:
                    response = (
                        "⚡ لبدء لعبة جديدة اكتب 'start'\n"
                        "🚫 لإنهاء اللعبة اكتب 'exit'"
                    )
                await self.save_games()
                return response

            # ... (معالجة الأوامر الأساسية تبقى كما هي)

            try:
                if not message.isdigit():
                    return "⚠ الرجاء إدخال رقم صحيح بين 1-9!"

                num = int(message)
                if not (1 <= num <= 9):
                    return "🔢 الرقم يجب أن يكون بين 1 و 9!"

                row, col = self.num_to_coords(num)
                if game.board[row][col] != " ":
                    return "⛔ هذا المربع محجوز! اختر رقمًا آخر:"

                game.board[row][col] = game.current_player
                game.last_activity = time.time()  # تحديث النشاط بعد الحركة

                if self.check_winner(game.board, game.current_player):
                    game.game_active = False
                    await self.save_games()
                    await self.highrise.send_message(slf.me, f"هناك لاعب فاز {conversation_id}")
                    return f"{self.format_board(game.board)}\n🎉 فاز اللاعب {game.current_player}!"

                if all(cell != " " for row in game.board for cell in row):
                    game.game_active = False
                    await self.save_games()
                    return f"{self.format_board(game.board)}\n🤝 تعادل!"

                if game.current_player == "X":
                    ai_row, ai_col = await self.ai_move(game.board)
                    game.board[ai_row][ai_col] = "O"
                    game.last_activity = time.time()  # تحديث النشاط بعد حركة البوت

                    if self.check_winner(game.board, "O"):
                        game.game_active = False
                        await self.save_games()
                        return f"{self.format_board(game.board)}\nفاز عليك بوت 🤣🤣🫵"

                    game.current_player = "X"

                await self.save_games()
                return f"{self.format_board(game.board)}\nدورك الان اختار رقم ({game.current_player})  👈 "

            except Exception as e:
                game.game_active = False
                await self.save_games()
                return f"🚨 خطأ حرج: {str(e)}"

# ... (بقية الوظائف تبقى كما هي)

    async def on_message(self, user_id: str, conversation_id: str, is_new_conversation: bool) -> None:
        try:
            conversation = await self.highrise.get_messages(conversation_id)
            message = conversation.messages[0].content

            response = await self.handle_game_logic(conversation_id, message)
            await self.highrise.send_message(conversation_id, response)
        except Exception as e:
            error_msg = f"حدث خطأ في المعالجة: {str(e)}"
            await self.highrise.send_message(conversation_id, error_msg)
        
