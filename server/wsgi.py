from app import app, socketio
from db import init_db

init_db()

if __name__ == "__main__":
    socketio.run(app)