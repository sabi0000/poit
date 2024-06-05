from threading import Lock
from flask import Flask, render_template, session, request, jsonify, url_for
from flask_socketio import SocketIO, emit, disconnect
import time
import random
import serial
import math
import json
import MySQLdb
import configparser as ConfigParser
import re

async_mode = None

#konfiguracie satabazy pomocou config.cfg
config = ConfigParser.ConfigParser()
config.read('config.cfg')
myhost = config.get('mysqlDB', 'host')
myuser = config.get('mysqlDB', 'user')
mypasswd = config.get('mysqlDB', 'passwd')
mydb = config.get('mysqlDB', 'db')
print(myhost)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode=async_mode)
thread = None
generating = False
thread_lock = Lock()
file_lock = Lock()

#nastavenie portu arduina a rychlost odosielania 115200
arduino_serial = serial.Serial('/dev/ttyACM0', 115200)
vzdialenost = 0
stav_brany = 0
zapisane = False
data_values = []
binary_values = []
flame_values = []

def background_thread(args):
    global data_values, binary_values, data, binary_data, count, flame_values
    count = 0

    while True:
        if generating:
            #prijimanie dat z arduina
            data = arduino_serial.readline().decode().strip()
            if data.startswith('{') and data.endswith('}'):
                try:
                    #analyza dat json
                    json_data = json.loads(data)
                    distance = json_data['distance']
                    flame_value = json_data['flameValue']
                    
                    #otvaranie rampy
                    binary_data = 1 if distance < 10 or flame_value < 100 else 0
                    #ukladanie dat do zoznamov
                    data_values.append(distance)
                    binary_values.append(binary_data)
                    flame_values.append(flame_value)

                    #posielanie dat cez socket
                    socketio.emit('my_response',
                                  {'distance': distance, 'flameValue': flame_value, 'binary_data': binary_data, 'count': count},
                                  namespace='/test')
                    count += 1
                #vypis pripadnej chyby na konzolu
                except json.JSONDecodeError:
                    print("Error decoding JSON data:", data)
            else:
                print("Incomplete data received:", data)
#definovanie ciest pre jednotlive stranky
@app.route('/')
def index():
    return render_template('index.html', async_mode=socketio.async_mode)

@app.route('/gauge', methods=['GET', 'POST'])
def gauge():
    return render_template('gauge.html', async_mode=socketio.async_mode)
    
@app.route('/graphlive', methods=['GET', 'POST'])
def graphlive():
    return render_template('graphlive.html', async_mode=socketio.async_mode)

@app.route('/graph', methods=['GET', 'POST'])
def graph():
    return render_template('graph.html', async_mode=socketio.async_mode)
#vypis udajov zo suboru
@app.route('/read')
def read_file():
    with open("static/files/test.txt", "r") as fo:
        rows = fo.readlines()
    return "<br>".join(rows)
    
@app.route('/read/<string:num>')
def readmyfile(num):
    with open("static/files/test.txt", "r") as fo:
        rows = fo.readlines()
    return rows[int(num) - 1]
#vypis poslednych zaznamenanych udajov zo suboru
@app.route('/read/last')
def read_last_line():
    with open("static/files/test.txt", "r") as fo:
        rows = fo.readlines()
    return rows[-1]
    
@socketio.on('my_event', namespace='/test')
def test_message(message):
    session['receive_count'] = session.get('receive_count', 0) + 1
    session['A'] = message['value']
    emit('my_response',
         {'data': message['value'], 'count': session['receive_count']})

@socketio.on('disconnect_request', namespace='/test')
def disconnect_request():
    session['receive_count'] = session.get('receive_count', 0) + 1
    emit('my_response',
         {'data': 'Disconnected!', 'count': session['receive_count']})
    disconnect()

#vypis udajov z databazy
@app.route('/db')
def db():
    #nastavenie pripojenia, vytvorenie kurzora a zvolenie konkretnej tabulky
    db_connection = MySQLdb.connect(host=myhost, user=myuser, passwd=mypasswd, db=mydb)
    cursor = db_connection.cursor()
    cursor.execute('''SELECT id, distance, binary_data, flame_value, created_at FROM udaje2''')
    rv = cursor.fetchall()
    cursor.close()
    db_connection.close()
    #vypis dat
    data = []
    for row in rv:
        data.append({
            "id": row[0],
            "distance": row[1],
            "binary_data": row[2],
            "flame_value": row[3],
            "created_at": row[4].strftime("%Y-%m-%d %H:%M:%S")
        })

    return jsonify(data)
#vypis poslednych zaznamenanych udajov z databazy
@app.route('/db/last')
def read_last_record():
    db_connection = MySQLdb.connect(host=myhost, user=myuser, passwd=mypasswd, db=mydb)
    cursor = db_connection.cursor()
    cursor.execute('''SELECT id, distance, binary_data, flame_value, created_at FROM udaje2 ORDER BY id DESC LIMIT 1''')
    row = cursor.fetchone()
    cursor.close()
    db_connection.close()

    if row is not None:
        data = {
            "id": row[0],
            "distance": row[1],
            "binary_data": row[2],
            "flame_value": row[3],
            "created_at": row[4].strftime("%Y-%m-%d %H:%M:%S")
        }
        return jsonify(data)
    else:
        return jsonify({"error": "No records found"})

@socketio.on('connect', namespace='/test')
def test_connect():
    global thread
    with thread_lock:
        if thread is None:
            thread = socketio.start_background_task(target=background_thread, args=session._get_current_object())
    emit('my_response', {'data': 'Connected', 'count': 0})

@socketio.on('disconnect', namespace='/test')
def test_disconnect():
    print('Client disconnected', request.sid)

@socketio.on('start_generation', namespace='/test')
def start_generation():
    global generating
    generating = True
#zapis udajov do suboru a do databazy
@socketio.on('stop_generation', namespace='/test')
def stop_generation():
    global data_values, binary_values, generating, data, flame_values
    generating = False
    

    #zapis udajov do databazy
    vzdialenosti_json = json.dumps(data_values)
    stavy_bran_json = json.dumps(binary_values)
    ohne_json = json.dumps(flame_values)
    db_connection = MySQLdb.connect(host=myhost, user=myuser, passwd=mypasswd, db=mydb)
    cursor = db_connection.cursor()
    cursor.execute('''INSERT INTO udaje2 (distance, binary_data, flame_value) VALUES (%s, %s, %s)''', (vzdialenosti_json, stavy_bran_json, ohne_json))
    db_connection.commit()
    cursor.close()
    db_connection.close()
    print('Data added successfully!')
    #zapis udajov do suboru
    data = []
    for idx, (current_data, binary_data, flame_data) in enumerate(zip(data_values, binary_values, flame_values), start=1):
        val = {'Vzdialenost': current_data, 'StavRampy': binary_data, 'StavPlamena': flame_data, 'countx': idx}
        data.append(val)

    with file_lock:
        try:
            with open("static/files/test.txt", "a+") as fo:
                fo.write(json.dumps(data) + '\n')
        except IOError as e:
            print(f"Error writing to file: {e}")

    return "done"
    data_values = []
    binary_values = []
    flame_values = []
    data = 0
    

    
if __name__ == '__main__':
    socketio.run(app, host="0.0.0.0", port=80, debug=True)
