from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
import os
import pymysql
import requests
from math import radians, cos, sin, sqrt, atan2
from urllib.parse import urlparse

app = Flask(__name__)
app.secret_key = 'your_secret_key'

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Parse JAWSDB_URL environment variable
jawsdb_url = "mysql://roqj6vrs3u9lbrbg:s0176e7q4crbscml@bqmayq5x95g1sgr9.cbetxkdyhwsb.us-east-1.rds.amazonaws.com:3306/tsp07coyqwcok0uk"
parsed_url = urlparse(jawsdb_url)
DB_HOST = parsed_url.hostname
DB_USER = parsed_url.username
DB_PASSWORD = parsed_url.password
DB_NAME = parsed_url.path[1:]  # Remove leading slash

# Geolocation configuration
PINNED_LOCATION = (53.483959, -2.244644)  # Latitude, Longitude of the pinned building
ALLOWED_RADIUS = 50  # in meters
GEO_API_URL = "https://ipapi.co/{ip}/json/"

def init_db():
    conn = pymysql.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
    cursor = conn.cursor()
    # Users table
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                      id INT AUTO_INCREMENT PRIMARY KEY,
                      username VARCHAR(255) UNIQUE NOT NULL,
                      password VARCHAR(255) NOT NULL,
                      role VARCHAR(50) NOT NULL)''')
    # Images table
    cursor.execute('''CREATE TABLE IF NOT EXISTS images (
                      id INT AUTO_INCREMENT PRIMARY KEY,
                      full_name VARCHAR(255) NOT NULL,
                      date_barred DATE NOT NULL,
                      date_bar_expires DATE NOT NULL,
                      reason TEXT NOT NULL)''')
    # Default admin user
    cursor.execute("INSERT IGNORE INTO users (username, password, role) VALUES ('admin', 'admin', 'administrator')")
    # Main super user
    cursor.execute("INSERT IGNORE INTO users (username, password, role) VALUES ('Kieran Jenkinson', '230885', 'administrator')")
    conn.commit()
    conn.close()

init_db()

# Helper functions
def get_db_connection():
    conn = pymysql.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME)
    return conn

def get_user_location(ip):
    """Fetch user location based on IP address."""
    try:
        response = requests.get(GEO_API_URL.format(ip=ip))
        if response.status_code == 200:
            data = response.json()
            return float(data.get('latitude')), float(data.get('longitude'))
    except Exception as e:
        print(f"Geolocation API error: {e}")
    return None

def calculate_distance(coord1, coord2):
    """Calculate distance between two geographic coordinates."""
    R = 6371e3  # Earth radius in meters
    lat1, lon1 = radians(coord1[0]), radians(coord1[1])
    lat2, lon2 = radians(coord2[0]), radians(coord2[1])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return R * c

# Routes
@app.route('/')
def index():
    if 'username' not in session:
        return redirect(url_for('login'))

    search_query = request.args.get('search', '').strip()
    sort_option = request.args.get('sort', '')

    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    query = 'SELECT * FROM images'
    params = []

    if search_query:
        query += ' WHERE full_name LIKE %s'
        params.append(f"%{search_query}%")

    sort_options = {
        'date_barred_asc': 'date_barred ASC',
        'date_barred_desc': 'date_barred DESC',
        'date_bar_expires_asc': 'date_bar_expires ASC',
        'date_bar_expires_desc': 'date_bar_expires DESC',
        'full_name_az': 'full_name ASC'
    }

    if sort_option in sort_options:
        query += f" ORDER BY {sort_options[sort_option]}"

    cursor.execute(query, params)
    records = cursor.fetchall()
    conn.close()

    return render_template('index.html', records=records, search_query=search_query, sort_option=sort_option)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE username = %s AND password = %s', (username, password))
        user = cursor.fetchone()
        conn.close()

        if user:
            if user['role'] != 'administrator':
                # Get client IP and location
                user_ip = request.remote_addr
                user_location = get_user_location(user_ip)

                if not user_location:
                    flash("Unable to determine your location. Access denied.")
                    return render_template('login.html')

                distance = calculate_distance(PINNED_LOCATION, user_location)

                if distance > ALLOWED_RADIUS:
                    flash("Access denied: You are not within the permitted location.")
                    return render_template('login.html')

            session['username'] = user['username']
            session['role'] = user['role']
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('role', None)
    return redirect(url_for('login'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if 'role' not in session or session['role'] != 'administrator':
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    if request.method == 'POST':
        if 'add_user' in request.form:
            username = request.form['username']
            password = request.form['password']
            role = request.form['role']
            try:
                cursor.execute('INSERT INTO users (username, password, role) VALUES (%s, %s, %s)', (username, password, role))
                conn.commit()
                flash('User added successfully')
            except pymysql.IntegrityError:
                flash('Username already exists')

        if 'add_record' in request.form:
            full_name = request.form['full_name']
            date_barred = request.form['date_barred']
            date_bar_expires = request.form['date_bar_expires']
            reason = request.form['reason']

            if not full_name.strip():
                flash('Full Name is required')
            elif not date_barred.strip():
                flash('Date Barred is required')
            elif not date_bar_expires.strip():
                flash('Date Bar Expires is required')
            elif not reason.strip():
                flash('Reason is required')
            else:
                cursor.execute('INSERT INTO images (full_name, date_barred, date_bar_expires, reason) VALUES (%s, %s, %s, %s)', 
                               (full_name, date_barred, date_bar_expires, reason))
                conn.commit()
                flash('Record added successfully')

    cursor.execute('SELECT * FROM users')
    users = cursor.fetchall()
    conn.close()
    return render_template('admin.html', users=users)

@app.route('/delete_user/<int:user_id>')
def delete_user(user_id):
    if 'role' not in session or session['role'] != 'administrator':
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
    conn.commit()
    conn.close()
    flash('User deleted successfully')
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True)
