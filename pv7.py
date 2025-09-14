from highrise import BaseBot
from highrise.__main__ import BotDefinition
from asyncio import create_task
import asyncio
import random
from datetime import datetime, timedelta
from highrise.models import User, CurrencyItem, Item, Message, SessionMetadata ,Position , AnchorPosition

class Bot(BaseBot):
    secret_words = ["سري", "برمجة", "مغامرة", "تعلم"]

    def __init__(self):
        super().__init__()
        self.games = {}
        self.conv = '1_on_1:687e1bce35a689e397576ef3:68c5abd6f04681fdf80aba5e'
        self.paid_users = set()  # لتخزين مستخدمين دفعوا
        self.special_user = "687e1bce35a689e397576ef3"
        self.xo_price = 50  # سعر لعبة XO

    async def on_start(self, SessionMetadata: SessionMetadata) -> None:
        print("Bot is starting...")
        await self.highrise.teleport(SessionMetadata.user_id, Position(x=7.5, y=2.25, z=17.5, facing='FrontLeft'))
        await self.highrise.send_emote('emote-timejump', SessionMetadata.user_id)
    async def on_user_join(self, user: User, position: Position | AnchorPosition) -> None:
        await self.highrise.chat(f"اهلا {user.username} ارسل رسالة فالخاص حتى تبداء اللعبة")
    
    async def on_whisper(self, user: User, message: str) -> None:
        if user.username == "5j___.l":
            await self.highrise.chat(f"{message}")
    async def on_chat(self, user: User, message: str) -> None:
        if message.lower().startswith("محفظتك") and user.username == "5j___.l":
            
            bot_wallet = await self.highrise.get_wallet()
            bot_amount = bot_wallet.content[0].amount
            await self.highrise.send_whisper(user.id, f"لدي {bot_amount}g")
        if message.lower().startswith("/tip ") and user.username == "5j___.l":
            parts = message.split(" ")
            if len(parts) != 2:
                await self.highrise.send_message(user.id, "Invalid command")
                return
            #checks if the amount is valid
            try:
                amount = int(parts[1])
            except:
                await self.highrise.chat("Invalid amount")
                return
            #checks if the bot has the amount
            bot_wallet = await self.highrise.get_wallet()
            bot_amount = bot_wallet.content[0].amount
            if bot_amount <= amount:
                await self.highrise.chat("Not enough funds")
                return
            #converts the amount to a string of bars and calculates the fee
            """Possible values are: "gold_bar_1",
            "gold_bar_5", "gold_bar_10", "gold_bar_50",
            "gold_bar_100", "gold_bar_500",
            "gold_bar_1k", "gold_bar_5000", "gold_bar_10k" """
            bars_dictionary = {10000: "gold_bar_10k",
                               5000: "gold_bar_5000",
                               1000: "gold_bar_1k",
                               500: "gold_bar_500",
                               100: "gold_bar_100",
                               50: "gold_bar_50",
                               10: "gold_bar_10",
                               5: "gold_bar_5",
                               1: "gold_bar_1"}
            fees_dictionary = {10000: 1000,
                               5000: 500,
                               1000: 100,
                               500: 50,
                               100: 10,
                               50: 5,
                               10: 1,
                               5: 1,
                               1: 1}
            #loop to check the highest bar that can be used and the amount of it needed
            tip = []
            total = 0
            for bar in bars_dictionary:
                if amount >= bar:
                    bar_amount = amount // bar
                    amount = amount % bar
                    for i in range(bar_amount):
                        tip.append(bars_dictionary[bar])
                        total = bar+fees_dictionary[bar]
            if total > bot_amount:
                await self.highrise.chat("Not enough funds")
                return
            tip_string = ",".join(tip)
            await self.highrise.tip_user(user.id, tip_string)
    # ---------------------- أدوات XO ----------------------
    def xo_board_to_text(self, board):
        def cell(val, idx):
            return val if val != ' ' else str(idx + 1)

        lines = []
        for r in range(3):
            row = ' | '.join(cell(board[r * 3 + col], r * 3 + col) for col in range(3))
            lines.append(row)
            if r < 2:
                lines.append('-' * 11)
        return '\n'.join(lines)

    def xo_check_winner(self, board):
        wins = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
        for a,b,c in wins:
            if board[a] != ' ' and board[a] == board[b] == board[c]:
                return board[a]
        return None

    def xo_full(self, board):
        return all(x != ' ' for x in board)

    def xo_minimax(self, board, player):
        winner = self.xo_check_winner(board)
        if winner == 'O':
            return 1
        if winner == 'X':
            return -1
        if self.xo_full(board):
            return 0

        if player == 'O':
            best = -2
            for i in range(9):
                if board[i] == ' ':
                    board[i] = 'O'
                    score = self.xo_minimax(board, 'X')
                    board[i] = ' '
                    best = max(best, score)
            return best
        else:
            best = 2
            for i in range(9):
                if board[i] == ' ':
                    board[i] = 'X'
                    score = self.xo_minimax(board, 'O')
                    board[i] = ' '
                    best = min(best, score)
            return best

    def xo_best_move(self, board):
        best_score = -2
        move = None
        for i in range(9):
            if board[i] == ' ':
                board[i] = 'O'
                score = self.xo_minimax(board, 'X')
                board[i] = ' '
                if score > best_score:
                    best_score = score
                    move = i
        return move

    async def check_xo_timeout(self, conversation_id):
        while self.games[conversation_id]['game_started'] and self.games[conversation_id]['type'] == 'xo':
            if datetime.now() - self.games[conversation_id]['game_start_time'] > timedelta(minutes=2):
                self.games[conversation_id]['game_started'] = False
                txt = "انتهت لعبة XO بسبب انتهاء المهلة الزمنية."
                await self.highrise.send_message(conversation_id, txt)
                break
            await asyncio.sleep(10)

    # ---------------------- أدوات Hangman ----------------------
    def get_current_word_state(self, secret_word, guessed_letters):
        return ' '.join([letter if letter in guessed_letters else '_' for letter in secret_word])

    async def check_game_timeout(self, conversation_id):
        while self.games[conversation_id]['game_started'] and self.games[conversation_id]['type'] == 'hangman':
            if datetime.now() - self.games[conversation_id]['game_start_time'] > timedelta(minutes=2):
                self.games[conversation_id]['game_started'] = False
                txt = f"انتهت لعبة الاحجية بسبب انتهاء المهلة الزمنية. الكلمة كانت: {self.games[conversation_id]['secret_word']}"
                await self.highrise.send_message(conversation_id, txt)
                break
            await asyncio.sleep(10)

    # ---------------------- معالجة الإكراميات ----------------------
    async def on_tip(self, sender: User, receiver: User, tip: CurrencyItem | Item) -> None:
        if isinstance(tip, CurrencyItem) and receiver.id == '68c5abd6f04681fdf80aba5e':
            await self.highrise.send_message(self.conv, f"@{sender.username} دفع مبلغ {tip.amount}")
            self.paid_users.add(sender.username)

    # ---------------------- معالجة الرسائل ----------------------
    async def on_message(self, user_id: str, conversation_id: str, is_new_conversation: bool) -> None:
        if is_new_conversation:
            txt = (
                f"ادفع {self.xo_price} ذهباً لبدء لعبة XO، في حال الفوز سوف تحصل على 500g\n"
                "اهلا انا هنا لخدمتك الاوامر\n"
                "\n اكتب احجية لتشغيل لعبة تخمين الحروف هذه اللعبة للتسلية لا تحصل على قولد من خلالها\n"
                "\n اكتب xo لتشغيل لعبة اكس او يتم اللعب عن طريق اختيار الارقام على اللوحة\n"
                "ملاحظة هامة :- \n الربح من خلال لعبة xo فقط \n التعادل يعني الخسارة\n اقل مبلغ للدفع 50 \n"
            )
            await self.highrise.send_message(conversation_id, txt)

        mssg = await self.highrise.get_messages(conversation_id)
        if not mssg.messages:
            return
        latest_message = mssg.messages[0]
        message_content = latest_message.content.strip()

        # الحصول على اسم المستخدم بشكل موثوق
        try:
          user_info = await self.webapi.get_user(latest_message.sender_id)
          sender_username = user_info.user.username
        except Exception as e:
          print(f"Error getting user info: {e}")
          sender_username = user_id  # استخدام user_id كاحتياطي

        if conversation_id not in self.games:
            self.games[conversation_id] = {
                'type': None,
                'secret_word': '',
                'guessed_letters': [],
                'game_started': False,
                'wrong_attempts': 0,
                'game_start_time': None,
                'xo_board': [' '] * 9,
                'xo_turn': 'X',
            }

        game = self.games[conversation_id]

        # معالجة أمر الإضافة من المستخدم المميز
        if message_content.startswith("اضف") and user_id == self.special_user:
            parts = message_content.split()
            if len(parts) >= 2:
                username_to_add = parts[1].strip('@')
                self.paid_users.add(username_to_add)
                print(f"تمت إضافة {username_to_add} إلى قائمة الدافعين عبر الأمر")
                await self.highrise.send_message(conversation_id, f"تمت إضافة {username_to_add} إلى قائمة الدافعين")
            return

        if message_content == 'احجية':
            if game['game_started'] and game['type'] == 'hangman':
                txt = "لعبة احجية قيد التشغيل بالفعل!" + \
                      " حاول تخمين الحروف: " + self.get_current_word_state(game['secret_word'], game['guessed_letters'])
            else:
                game['type'] = 'hangman'
                game['guessed_letters'] = []
                game['game_started'] = True
                game['wrong_attempts'] = 0
                game['secret_word'] = random.choice(self.secret_words)
                game['game_start_time'] = datetime.now()
                create_task(self.check_game_timeout(conversation_id))
                txt = f"لعبة جديدة بدأت! حاول تخمين الكلمة: {self.get_current_word_state(game['secret_word'], game['guessed_letters'])}"
            await self.highrise.send_message(conversation_id, txt)
            return

        if message_content.lower() in ['xo', 'x o', 'اكس او', 'XO', 'Xo']:
            if sender_username not in self.paid_users:
                await self.highrise.send_message(conversation_id, f"يجب دفع {self.xo_price} ذهباً لبدء لعبة XO. ارسل إكرامية {self.xo_price} ذهباً للبوت.")
                return
                
            if game['game_started'] and game['type'] == 'xo':
                txt = "لعبة XO قيد التشغيل بالفعل! ارسل رقم 1-9 لوضع علامتك."
                await self.highrise.send_message(conversation_id, txt)
                return
            game['type'] = 'xo'
            game['xo_board'] = [' '] * 9
            game['xo_turn'] = 'X'
            game['game_started'] = True
            game['game_start_time'] = datetime.now()
            create_task(self.check_xo_timeout(conversation_id))
            board_txt = self.xo_board_to_text(game['xo_board'])
            txt = "بدأت لعبة XO! أنت X والبوت O. أرسل رقم 1-9 لوضع علامتك:\n" + board_txt
            await self.highrise.send_message(conversation_id, txt)
            return

        if game['game_started'] and game['type'] == 'xo':
            if len(message_content) == 1 and message_content.isdigit():
                idx = int(message_content) - 1
                if idx < 0 or idx > 8:
                    await self.highrise.send_message(conversation_id, "اختر رقما بين 1 و 9.")
                    return
                if game['xo_board'][idx] != ' ':
                    await self.highrise.send_message(conversation_id, "الخانة مشغولة! اختر خانة أخرى.")
                    return

                game['xo_board'][idx] = 'X'
                winner = self.xo_check_winner(game['xo_board'])
                if winner == 'X':
                    board_txt = self.xo_board_to_text(game['xo_board'])
                    txt = board_txt + "\n\nلقد فزت! مبروك! احصل على ذهبك من @mr._.cat"
                    await self.highrise.send_message(self.conv, f" @{sender_username} قد فاز")
                    if sender_username in self.paid_users:
                      await self.highrise.send_message(self.conv, f" @{sender_username} فاز ودفع")
                    game['game_started'] = False
                    await self.highrise.send_message(conversation_id, txt)
                    return
                if self.xo_full(game['xo_board']):
                    board_txt = self.xo_board_to_text(game['xo_board'])
                    txt = board_txt + "\n\nتعادل! لقد اقتربت هذه المرة، هل هذا افضل ما لديك "
                    game['game_started'] = False
                    await self.highrise.send_message(conversation_id, txt)
                    return

                bot_move = self.xo_best_move(game['xo_board'])
                if bot_move is not None:
                    game['xo_board'][bot_move] = 'O'

                winner = self.xo_check_winner(game['xo_board'])
                board_txt = self.xo_board_to_text(game['xo_board'])
                if winner == 'O':
                    # التحقق إذا كان المستخدم دفع قبل طباعة الخسارة
                    if sender_username in self.paid_users:
                        await self.highrise.send_message(self.conv, f"@{sender_username} دفع وخسر في XO")
                    txt = board_txt + f"\n\nالبوت اختار الخانة {bot_move+1} وفاز! خل هذا افضل ما لديك توقعتك اذكى من ذلك"
                    game['game_started'] = False
                elif self.xo_full(game['xo_board']):
                    txt = board_txt + "\n\nتعادل! لقد اقتربت هذه المرة، توقعت ان اخسر"
                    game['game_started'] = False
                else:
                    txt = board_txt + f"\n\nالبوت اختار الخانة {bot_move+1} دورك  ارسل رقم 1-9."

                await self.highrise.send_message(conversation_id, txt)
                return
            else:
                await self.highrise.send_message(conversation_id, "خلال لعبة XO، ارسل رقم واحد من 1 إلى 9 لوضع علامتك.")
                return

        if game['game_started'] and game['type'] == 'hangman':
            message = message_content
            if len(message) == 1:
                letter = message
                if letter in game['secret_word']:
                    if letter not in game['guessed_letters']:
                        game['guessed_letters'].append(letter)
                        txt = f"حرف صحيح! الكلمة: {self.get_current_word_state(game['secret_word'], game['guessed_letters'])}"
                    else:
                        txt = f"لقد خمنت هذا الحرف مسبقًا! الكلمة: {self.get_current_word_state(game['secret_word'], game['guessed_letters'])}"
                else:
                    game['wrong_attempts'] += 1
                    txt = f"حرف غير صحيح. حاول مرة أخرى. المحاولات الخاطئة: {game['wrong_attempts']}/5. الكلمة: {self.get_current_word_state(game['secret_word'], game['guessed_letters'])}"

                if all(letter in game['guessed_letters'] for letter in game['secret_word']):
                    txt = f"مبروك! لقد خمنت الكلمة الصحيحة: {game['secret_word']}"
                    game['game_started'] = False
                elif game['wrong_attempts'] >= 5:
                    txt = f"لقد تجاوزت الحد الأقصى للمحاولات الخاطئة. اللعبة انتهت. الكلمة كانت: {game['secret_word']}"
                    game['game_started'] = False

                await self.highrise.send_message(conversation_id, txt)
                return
            else:
                return

        return
