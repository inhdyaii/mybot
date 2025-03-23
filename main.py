import os
import yt_dlp
from collections import deque
import asyncio
import subprocess
import threading
import time
import socket
import signal
import random
from dotenv import load_dotenv
from flask import Flask, request  # تمت إضافة استيراد Flask

app = Flask(__name__)  # تهيئة تطبيق Flask

load_dotenv()

ICECAST_HOST = os.getenv("ICECAST_HOST")
ICECAST_PORT = os.getenv("ICECAST_PORT")
ICECAST_USER = os.getenv("ICECAST_USER")
ICECAST_PASSWORD = os.getenv("ICECAST_PASSWORD")
ICECAST_MOUNT = os.getenv("ICECAST_MOUNT")
ICECAST_URL = f"icecast://{ICECAST_USER}:{ICECAST_PASSWORD}@{ICECAST_HOST}:{ICECAST_PORT}/{ICECAST_MOUNT.strip()}"

SONG_QUEUE = deque()
current_process = None
current_song = None
queue_lock = asyncio.Lock()

@app.route('/health')  # إضافة نقطة نهاية للصحة
def health_check():
    return "OK", 200

async def search_ytdlp_async(query, ydl_opts):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _extract(query, ydl_opts))

def _extract(query, ydl_opts):
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(query, download=False)

async def stream_next_song(loop):
    global current_process, current_song
    await asyncio.sleep(0.3)

    async with queue_lock:
        if current_process is not None:
            return

        if not SONG_QUEUE:
            await add_random_song(loop)

        if not SONG_QUEUE:
            return

        current_song = SONG_QUEUE.popleft()
        audio_url, title = current_song
        print(f"البث الآن: {title}")

        ffmpeg_command = [
            "ffmpeg",
            "-re",
            "-i", audio_url,
            "-acodec", "libmp3lame",
            "-ab", "128k",
            "-f", "mp3",
            ICECAST_URL
        ]

        proc = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        current_process = proc

        def wait_and_continue():
            global current_process, current_song
            proc.wait()
            current_process = None
            current_song = None
            time.sleep(0.5)

            if not SONG_QUEUE:
                queries = ["random music", "pop songs", "latest hits", "trending music"]
                random_query = random.choice(queries)
                future = asyncio.run_coroutine_threadsafe(
                    do_play(random_query, loop, immediate=True), loop
                )
                try:
                    response = future.result(timeout=10)
                    print("إضافة أغنية عشوائية:", response)
                except Exception as e:
                    print("فشل إضافة أغنية عشوائية:", e)

            asyncio.run_coroutine_threadsafe(stream_next_song(loop), loop).result()

        threading.Thread(target=wait_and_continue, daemon=True).start()

async def add_random_song(loop):
    queries = ["random music", "pop songs", "latest hits", "trending music"]
    random_query = random.choice(queries)
    response = await do_play(random_query, loop, immediate=True)
    if "تمت إضافة" not in response:
        print("فشل إضافة أغنية عشوائية:", response)

async def do_play(song_query: str, loop, immediate=False) -> str:
    ydl_options = {
        "format": "bestaudio/best",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "extractor_args": {"youtube": {"player_client": ["android"]}},
        "nocheckcertificate": True,
        "ignoreerrors": True,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        query = "ytsearch1:" + song_query
        results = await search_ytdlp_async(query, ydl_options)
        tracks = results.get("entries", [])

        if not tracks:
            return "لم يتم العثور على نتائج."

        first_track = tracks[0]
        audio_url = first_track["url"]
        title = first_track.get("title", "بدون عنوان")

        async with queue_lock:
            if immediate:
                SONG_QUEUE.appendleft((audio_url, title))
            else:
                SONG_QUEUE.append((audio_url, title))

        response = f"تمت إضافة الأغنية إلى القائمة: {title}"

        if current_process is None:
            await stream_next_song(loop)
        elif immediate:
            current_process.send_signal(signal.SIGINT)

        return response
    except Exception as e:
        return f"حدث خطأ أثناء البحث: {str(e)}"

async def do_skip() -> str:
    global current_process
    if current_process is not None:
        current_process.send_signal(signal.SIGINT)
        return "جارٍ التخطي إلى الأغنية التالية..."
    return "لا يوجد بث جاري."

async def do_stop() -> str:
    global current_process, current_song
    async with queue_lock:
        if current_process is not None:
            current_process.kill()
            current_process = None

        SONG_QUEUE.clear()
        current_song = None
    return "تم إيقاف البث ومسح قائمة الانتظار."

async def do_queue() -> str:
    message = []
    async with queue_lock:
        if current_song:
            message.append(f"الآن يعزف: {current_song[1]}")
        else:
            message.append("لا يوجد أغنية تعزف حاليا.")

        if SONG_QUEUE:
            message.append("\nقائمة الانتظار:")
            for idx, (url, title) in enumerate(SONG_QUEUE, start=1):
                message.append(f"{idx}. {title}")
        else:
            message.append("\nقائمة الانتظار فارغة.")
    return "\n".join(message)

async def do_remove(position: int) -> str:
    async with queue_lock:
        if position < 1 or position > len(SONG_QUEUE):
            return "رقم غير صحيح في القائمة."

        removed_song = SONG_QUEUE[position-1]
        del SONG_QUEUE[position-1]
        return f"تم حذف الأغنية: {removed_song[1]}"

def terminal_command_listener(loop):
    print("الاستماع للأوامر من التيرمنل. الردود ستظهر هنا.")
    while True:
        try:
            command = input("أدخل الأمر (play <song> | playnow <song> | skip | stop | queue | remove <num>): ").strip()
        except EOFError:
            break

        if command.lower().startswith("playnow "):
            song_query = command[8:].strip()
            future = asyncio.run_coroutine_threadsafe(do_play(song_query, loop, immediate=True), loop)
            response = future.result()
            print(response)
        elif command.lower().startswith("play "):
            song_query = command[5:].strip()
            future = asyncio.run_coroutine_threadsafe(do_play(song_query, loop), loop)
            response = future.result()
            print(response)
        elif command.lower() == "skip":
            future = asyncio.run_coroutine_threadsafe(do_skip(), loop)
            response = future.result()
            print(response)
        elif command.lower() == "stop":
            future = asyncio.run_coroutine_threadsafe(do_stop(), loop)
            response = future.result()
            print(response)
        elif command.lower() == "queue":
            future = asyncio.run_coroutine_threadsafe(do_queue(), loop)
            response = future.result()
            print(response)
        elif command.lower().startswith("remove "):
            try:
                position = int(command[7:].strip())
                future = asyncio.run_coroutine_threadsafe(do_remove(position), loop)
                response = future.result()
                print(response)
            except ValueError:
                print("الرجاء إدخال رقم صحيح")
        else:
            print("أمر غير معروف. الأوامر المتاحة: play <song>, playnow <song>, skip, stop, queue, remove <num>.")

def socket_command_listener(loop):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('localhost', 12345))
    s.listen(1)
    print("Socket command listener active on port 12345.")

    while True:
        conn, addr = s.accept()
        with conn:
            data = conn.recv(1024)
            if not data:
                continue

            command = data.decode().strip()
            print("Received command:", command)

            if command.lower().startswith("playnow "):
                song_query = command[8:].strip()
                future = asyncio.run_coroutine_threadsafe(
                    do_play(song_query, loop, immediate=True), loop
                )
                response = future.result()
                conn.sendall(response.encode())
            elif command.lower().startswith("play "):
                song_query = command[5:].strip()
                future = asyncio.run_coroutine_threadsafe(
                    do_play(song_query, loop), loop
                )
                response = future.result()
                conn.sendall(response.encode())
            elif command.lower() == "skip":
                future = asyncio.run_coroutine_threadsafe(do_skip(), loop)
                response = future.result()
                conn.sendall(response.encode())
            elif command.lower() == "stop":
                future = asyncio.run_coroutine_threadsafe(do_stop(), loop)
                response = future.result()
                conn.sendall(response.encode())
            elif command.lower() == "queue":
                future = asyncio.run_coroutine_threadsafe(do_queue(), loop)
                response = future.result()
                conn.sendall(response.encode())
            elif command.lower().startswith("remove "):
                try:
                    position = int(command[7:].strip())
                    future = asyncio.run_coroutine_threadsafe(
                        do_remove(position), loop
                    )
                    response = future.result()
                    conn.sendall(response.encode())
                except ValueError:
                    conn.sendall("الرجاء إدخال رقم صحيح".encode())
            else:
                conn.sendall("أمر غير معروف".encode())



def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # بدء خادم Flask في thread منفصل (الجزء المصحح)
    flask_thread = threading.Thread(
        target=lambda: app.run(
            host='0.0.0.0',
            port=int(os.environ.get('PORT', 10000))  # قوس إغلاق هنا
        ),  # ثم فاصلة
        daemon=True
    )
    flask_thread.start()

    terminal_thread = threading.Thread(target=terminal_command_listener, args=(loop,), daemon=True)
    terminal_thread.start()

    socket_thread = threading.Thread(target=socket_command_listener, args=(loop,), daemon=True)
    socket_thread.start()

    try:
        asyncio.run_coroutine_threadsafe(add_random_song(loop), loop)
        loop.run_forever()
    except KeyboardInterrupt:
        if current_process:
            current_process.kill()
        loop.close()


if __name__ == "__main__":
    main()
