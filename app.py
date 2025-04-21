from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
import json
import os
import logging
from datetime import datetime, timedelta
import csv
from io import StringIO
import portalocker
import stat  # For setting file permissions

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'secure-store-tracker-2025'

# Configure logging
logging.basicConfig(
    filename='store_tracker.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# File paths
DATA_DIR = 'data'
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
EVENTS_FILE = os.path.join(DATA_DIR, 'events.json')
TASKS_FILE = os.path.join(DATA_DIR, 'tasks.json')
COMPLETED_TASKS_FILE = os.path.join(DATA_DIR, 'completed_tasks.json')
STAFF_FILE = os.path.join(DATA_DIR, 'staff.json')
PAYROLL_FILE = os.path.join(DATA_DIR, 'payroll.json')
INVENTORY_FILE = os.path.join(DATA_DIR, 'inventory.json')
BORROW_FILE = os.path.join(DATA_DIR, 'borrow.json')
ORDERS_FILE = os.path.join(DATA_DIR, 'orders.json')

# Initialize data files with proper permissions
def initialize_files():
    try:
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
            os.chmod(DATA_DIR, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
            logging.info(f"Created {DATA_DIR} directory with full permissions")
    except PermissionError as e:
        logging.error(f"Failed to create {DATA_DIR} directory: {str(e)}")
        raise

    default_data = {
        USERS_FILE: {'users': [{'username': 'admin', 'password': 'admin123', 'role': 'manager'}]},
        EVENTS_FILE: [],
        TASKS_FILE: [],
        COMPLETED_TASKS_FILE: [],
        STAFF_FILE: [],
        PAYROLL_FILE: [],
        INVENTORY_FILE: [],
        BORROW_FILE: [],
        ORDERS_FILE: []
    }
    for file, default in default_data.items():
        if not os.path.exists(file):
            try:
                with open(file, 'w') as f:
                    json.dump(default, f, indent=4)
                os.chmod(file, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
                logging.info(f"Initialized {file} with full permissions")
            except PermissionError as e:
                logging.error(f"Failed to initialize {file}: {str(e)}")
                raise

initialize_files()

# Helper functions
def load_data(file_path):
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except PermissionError as e:
        print(f"ERROR: No permission to read {file_path}. Details: {e}")
        logging.error(f"Permission error reading {file_path}: {str(e)}")
        return {}
    except Exception as e:
        print(f"Unexpected error reading {file_path}: {e}")
        logging.error(f"Error reading {file_path}: {str(e)}")
        return {}

def save_data(file_path, data):
    try:
        with open(file_path, 'w') as f:
            with portalocker.Lock(file_path, timeout=5, mode='w'):
                json.dump(data, f, indent=4)
        os.chmod(file_path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        logging.info(f"Saved data to {file_path}")
    except PermissionError as e:
        logging.error(f"Permission denied when saving {file_path}: {str(e)}")
        raise Exception(f"Permission denied: Cannot write to {file_path}. Check file permissions.")
    except (portalocker.exceptions.LockException, Exception) as e:
        logging.error(f"Error saving {file_path}: {str(e)}")
        raise

def get_unique_items(file_path, key='name'):
    data = load_data(file_path)
    return sorted(list(set(item[key] for item in data if key in item)))

def calculate_hours(time_in, time_out):
    if not time_in or not time_out:
        return 0
    try:
        in_time = datetime.strptime(time_in, '%Y-%m-%d %H:%M:%S')
        out_time = datetime.strptime(time_out, '%Y-%m-%d %H:%M:%S')
        return (out_time - in_time).total_seconds() / 3600  # Hours
    except ValueError:
        return 0

# Routes
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if not username or not password:
            logging.warning(f"Login attempt with empty credentials")
            return render_template('login.html', error='Username and password are required')
        users_data = load_data(USERS_FILE)
        for user in users_data.get('users', []):
            if user['username'] == username and user['password'] == password:
                session['username'] = username
                session['role'] = user.get('role', 'staff')
                logging.info(f"User {username} logged in with role {session['role']}")
                return redirect(url_for('dashboard'))
        logging.warning(f"Failed login attempt for username: {username}")
        return render_template('login.html', error='Invalid credentials')
    return render_template('login.html', error=None)

@app.route('/dashboard', methods=['GET'])
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    events = load_data(EVENTS_FILE)
    tasks = load_data(TASKS_FILE)
    completed_tasks = load_data(COMPLETED_TASKS_FILE)
    staff_logs = load_data(STAFF_FILE)
    payroll_data = load_data(PAYROLL_FILE)
    users_data = load_data(USERS_FILE)
    
    # Debug logging
    logging.info(f"Payroll Data: {payroll_data}")
    logging.info(f"Users Data: {users_data}")
    logging.info(f"Staff Logs: {staff_logs}")
    
    # Check for overdue tasks
    notifications = []
    for task in tasks:
        task_date = datetime.strptime(task['date'], '%Y-%m-%d')
        if (datetime.now() - task_date).days > 1:  # Overdue after 1 day
            notifications.append(f"Task '{task['description']}' is overdue (Due: {task['date']})!")
    
    if session['role'] != 'manager':
        staff_logs = [log for log in staff_logs if log.get('name') == session['username']]
        payroll_data = [pay for pay in payroll_data if pay.get('name') == session['username']]
    
    staff_names = get_unique_items(STAFF_FILE, 'name')
    
    return render_template('dashboard.html', 
                          events=events, 
                          tasks=tasks, 
                          completed_tasks=completed_tasks, 
                          staff_logs=staff_logs, 
                          payroll_data=payroll_data,
                          users=users_data.get('users', []),
                          staff_names=staff_names,
                          notifications=notifications,
                          role=session['role'])

@app.route('/inventory', methods=['GET'])
def inventory():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    inventory = load_data(INVENTORY_FILE)
    borrow_history = load_data(BORROW_FILE)
    item_names = get_unique_items(INVENTORY_FILE, 'name')
    
    notifications = []
    for borrow in borrow_history:
        if not borrow.get('returned', False):
            borrow_date = datetime.strptime(borrow['borrow_date'], '%Y-%m-%d')
            if (datetime.now() - borrow_date).days > 7:
                notifications.append(f"Item {borrow['item']} borrowed by {borrow['borrowed_by']} is overdue!")
    
    return render_template('inventory.html', 
                          inventory=inventory, 
                          borrow_history=borrow_history, 
                          item_names=item_names, 
                          notifications=notifications,
                          role=session['role'])

@app.route('/orders', methods=['GET'])
def orders():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    inventory = load_data(INVENTORY_FILE)
    orders = load_data(ORDERS_FILE)
    item_names = get_unique_items(INVENTORY_FILE, 'name')
    
    return render_template('orders.html', 
                          inventory=inventory, 
                          orders=orders, 
                          item_names=item_names,
                          role=session['role'])

# AJAX Routes
@app.route('/add_event', methods=['POST'])
def add_event():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    event_date = request.form.get('event_date')
    event_desc = request.form.get('event_description')
    if not event_date or not event_desc:
        return jsonify({'error': 'Event date and description are required'}), 400
    
    events = load_data(EVENTS_FILE)
    events.append({'date': event_date, 'description': event_desc, 'added_by': session['username']})
    save_data(EVENTS_FILE, events)
    
    events_html = ''.join([f"<li>{event['date']}: {event['description']} (by {event['added_by']})</li>" for event in events])
    return jsonify({'events': events_html})

@app.route('/add_task', methods=['POST'])
def add_task():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    task_time = request.form.get('task_time')
    task_date = request.form.get('task_date')
    task_desc = request.form.get('task_description')
    if not all([task_time, task_date, task_desc]):
        return jsonify({'error': 'Task time, date, and description are required'}), 400
    
    tasks = load_data(TASKS_FILE)
    tasks.append({'time': task_time, 'date': task_date, 'description': task_desc, 'status': 'pending'})
    save_data(TASKS_FILE, tasks)
    
    tasks_html = ''.join([f"<li data-id='{i}'>{task['time']} on {task['date']}: {task['description']} <button class='complete-task' data-id='{i}'>Complete</button></li>" for i, task in enumerate(tasks)])
    return jsonify({'tasks': tasks_html})

@app.route('/complete_task', methods=['POST'])
def complete_task():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    task_id = request.form.get('task_id')
    if not task_id or not task_id.isdigit():
        return jsonify({'error': 'Invalid task ID'}), 400
    
    task_id = int(task_id)
    tasks = load_data(TASKS_FILE)
    completed_tasks = load_data(COMPLETED_TASKS_FILE)
    
    if task_id < 0 or task_id >= len(tasks):
        return jsonify({'error': 'Task not found'}), 404
    
    completed_task = tasks.pop(task_id)
    completed_task['status'] = 'completed'
    completed_task['completed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    completed_tasks.append(completed_task)
    save_data(TASKS_FILE, tasks)
    save_data(COMPLETED_TASKS_FILE, completed_tasks)
    
    tasks_html = ''.join([f"<li data-id='{i}'>{task['time']} on {task['date']}: {task['description']} <button class='complete-task' data-id='{i}'>Complete</button></li>" for i, task in enumerate(tasks)])
    completed_tasks_html = ''.join([f"<li>{task['time']} on {task['date']}: {task['description']} (Completed: {task['completed_at']})</li>" for task in completed_tasks])
    return jsonify({'tasks': tasks_html, 'completed_tasks': completed_tasks_html})

@app.route('/log_staff_time', methods=['POST'])
def log_staff_time():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    staff_name = request.form.get('staff_name')
    time_type = request.form.get('time_type')
    if not staff_name or time_type not in ['in', 'out']:
        return jsonify({'error': 'Staff name and time type are required'}), 400
    
    staff_logs = load_data(STAFF_FILE)
    payroll_data = load_data(PAYROLL_FILE)
    users_data = load_data(USERS_FILE)
    
    # Check for existing open time-in
    last_log = next((log for log in reversed(staff_logs) if log['name'] == staff_name and log['time_out'] is None), None)
    if time_type == 'in' and last_log:
        return jsonify({'error': f'{staff_name} already has an open time-in'}), 400
    if time_type == 'out' and not last_log:
        return jsonify({'error': f'No open time-in found for {staff_name}'}), 400
    
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if time_type == 'in':
        staff_logs.append({'name': staff_name, 'time_in': current_time, 'time_out': None})
    else:
        last_log['time_out'] = current_time
        hours = calculate_hours(last_log['time_in'], last_log['time_out'])
        if hours > 0 and session['role'] == 'manager':
            rate = 15.0  # Hourly rate (configurable)
            amount = hours * rate
            payroll_data.append({'name': staff_name, 'amount': round(amount, 2), 'date': datetime.now().strftime('%Y-%m-%d')})
            save_data(PAYROLL_FILE, payroll_data)
    
    save_data(STAFF_FILE, staff_logs)
    
    staff_logs_html = ''.join([f"<li>{log['name']} - In: {log['time_in'] or 'N/A'} | Out: {log['time_out'] or 'N/A'}</li>" for log in staff_logs if session['role'] == 'manager' or log['name'] == session['username']])
    
    # Generate payroll HTML for the table
    payroll_html = ''
    if session['role'] == 'manager':
        payroll_html = ''.join([
            f"<tr><td>{next((user['role'] for user in users_data['users'] if user['username'] == pay['name']), 'Unknown')}</td>" +
            f"<td>₱{(pay['amount'] * 58):.2f}</td>" +
            f"<td>{next((log['time_in'] for log in reversed(staff_logs) if log['name'] == pay['name']), 'N/A')} / " +
            f"{next((log['time_out'] for log in reversed(staff_logs) if log['name'] == pay['name'] and log['time_out'] is not None), 'N/A')}</td></tr>"
            for pay in payroll_data
        ])
    
    return jsonify({'staff_logs': staff_logs_html, 'payroll': payroll_html})

@app.route('/add_item', methods=['POST'])
def add_item():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    item_name = request.form.get('item_name')
    quantity = request.form.get('quantity')
    if not item_name or not quantity or not quantity.isdigit() or int(quantity) < 0:
        return jsonify({'error': 'Item name and valid quantity are required'}), 400
    
    inventory = load_data(INVENTORY_FILE)
    if any(item['name'] == item_name for item in inventory):
        return jsonify({'error': f'Item {item_name} already exists'}), 400
    
    inventory.append({
        'name': item_name,
        'quantity': int(quantity),
        'added_by': session['username'],
        'added_date': datetime.now().strftime('%Y-%m-%d')
    })
    save_data(INVENTORY_FILE, inventory)
    
    inventory_html = ''.join([f"<tr><td>{item['name']}</td><td {'class=\"low-stock\"' if item['quantity'] < 5 else ''}>{item['quantity']}</td><td>{item['added_by']}</td><td>{item['added_date']}</td></tr>" for item in inventory])
    item_names_html = '<option value="" disabled selected>Select Item</option>' + ''.join([f"<option value='{item['name']}'>{item['name']}</option>" for item in inventory])
    return jsonify({'inventory': inventory_html, 'item_names': item_names_html})

@app.route('/borrow_item', methods=['POST'])
def borrow_item():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    item_name = request.form.get('item_name')
    quantity = request.form.get('quantity')
    if not item_name or not quantity or not quantity.isdigit() or int(quantity) <= 0:
        return jsonify({'error': 'Item name and valid quantity are required'}), 400
    
    quantity = int(quantity)
    inventory = load_data(INVENTORY_FILE)
    borrow_history = load_data(BORROW_FILE)
    
    item = next((item for item in inventory if item['name'] == item_name), None)
    if not item:
        return jsonify({'error': f'Item {item_name} not found'}), 404
    if item['quantity'] < quantity:
        return jsonify({'error': f'Insufficient stock for {item_name}. Available: {item['quantity']}'}), 400
    
    # Check for existing borrow
    if any(borrow['item'] == item_name and borrow['borrowed_by'] == session['username'] and not borrow['returned'] for borrow in borrow_history):
        return jsonify({'error': f'You have already borrowed {item_name}'}), 400
    
    item['quantity'] -= quantity
    borrow_history.append({
        'item': item_name,
        'quantity': quantity,
        'borrowed_by': session['username'],
        'borrow_date': datetime.now().strftime('%Y-%m-%d'),
        'returned': False
    })
    save_data(INVENTORY_FILE, inventory)
    save_data(BORROW_FILE, borrow_history)
    
    inventory_html = ''.join([f"<tr><td>{item['name']}</td><td {'class=\"low-stock\"' if item['quantity'] < 5 else ''}>{item['quantity']}</td><td>{item['added_by']}</td><td>{item['added_date']}</td></tr>" for item in inventory])
    borrow_html = ''.join([f"<tr><td>{borrow['item']}</td><td>{borrow['quantity']}</td><td>{borrow['borrowed_by']}</td><td>{borrow['borrow_date']}</td><td>{'Returned' if borrow['returned'] else 'Borrowed'}</td><td>{'<button class=\"return-item\" data-id=\"' + str(i) + '\">Return</button>' if not borrow['returned'] else 'Returned on ' + borrow['return_date']}</td></tr>" for i, borrow in enumerate(borrow_history)])
    
    notifications = []
    for borrow in borrow_history:
        if not borrow.get('returned', False):
            borrow_date = datetime.strptime(borrow['borrow_date'], '%Y-%m-%d')
            if (datetime.now() - borrow_date).days > 7:
                notifications.append(f"<div class='notification'>Item {borrow['item']} borrowed by {borrow['borrowed_by']} is overdue!</div>")
    notifications_html = ''.join(notifications) if notifications else "<div class='notification success'>No overdue items.</div>"
    
    return jsonify({'inventory': inventory_html, 'borrow_history': borrow_html, 'notifications': notifications_html})

@app.route('/return_item', methods=['POST'])
def return_item():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    borrow_id = request.form.get('borrow_id')
    if not borrow_id or not borrow_id.isdigit():
        return jsonify({'error': 'Invalid borrow ID'}), 400
    
    borrow_id = int(borrow_id)
    inventory = load_data(INVENTORY_FILE)
    borrow_history = load_data(BORROW_FILE)
    
    if borrow_id < 0 or borrow_id >= len(borrow_history):
        return jsonify({'error': 'Borrow record not found'}), 404
    
    borrow_entry = borrow_history[borrow_id]
    if borrow_entry['returned']:
        return jsonify({'error': 'Item already returned'}), 400
    if borrow_entry['borrowed_by'] != session['username'] and session['role'] != 'manager':
        return jsonify({'error': 'Unauthorized to return this item'}), 403
    
    for item in inventory:
        if item['name'] == borrow_entry['item']:
            item['quantity'] += borrow_entry['quantity']
            break
    
    borrow_entry['returned'] = True
    borrow_entry['return_date'] = datetime.now().strftime('%Y-%m-%d')
    save_data(INVENTORY_FILE, inventory)
    save_data(BORROW_FILE, borrow_history)
    
    inventory_html = ''.join([f"<tr><td>{item['name']}</td><td {'class=\"low-stock\"' if item['quantity'] < 5 else ''}>{item['quantity']}</td><td>{item['added_by']}</td><td>{item['added_date']}</td></tr>" for item in inventory])
    borrow_html = ''.join([f"<tr><td>{borrow['item']}</td><td>{borrow['quantity']}</td><td>{borrow['borrowed_by']}</td><td>{borrow['borrow_date']}</td><td>{'Returned' if borrow['returned'] else 'Borrowed'}</td><td>{'<button class=\"return-item\" data-id=\"' + str(i) + '\">Return</button>' if not borrow['returned'] else 'Returned on ' + borrow['return_date']}</td></tr>" for i, borrow in enumerate(borrow_history)])
    
    notifications = []
    for borrow in borrow_history:
        if not borrow.get('returned', False):
            borrow_date = datetime.strptime(borrow['borrow_date'], '%Y-%m-%d')
            if (datetime.now() - borrow_date).days > 7:
                notifications.append(f"<div class='notification'>Item {borrow['item']} borrowed by {borrow['borrowed_by']} is overdue!</div>")
    notifications_html = ''.join(notifications) if notifications else "<div class='notification success'>No overdue items.</div>"
    
    return jsonify({'inventory': inventory_html, 'borrow_history': borrow_html, 'notifications': notifications_html})

@app.route('/add_order', methods=['POST'])
def add_order():
    if 'username' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    item_name = request.form.get('item_name')
    quantity = request.form.get('quantity')
    price = request.form.get('price')
    if not item_name or not quantity or not quantity.isdigit() or int(quantity) <= 0 or not price or not price.replace('.', '', 1).isdigit() or float(price) < 0:
        return jsonify({'error': 'Item name, valid quantity, and price are required'}), 400
    
    quantity = int(quantity)
    price = float(price)
    inventory = load_data(INVENTORY_FILE)
    orders = load_data(ORDERS_FILE)
    
    item = next((item for item in inventory if item['name'] == item_name), None)
    if not item:
        return jsonify({'error': f'Item {item_name} not found'}), 404
    if item['quantity'] < quantity:
        return jsonify({'error': f'Insufficient stock for {item_name}. Available: {item['quantity']}'}), 400
    
    item['quantity'] -= quantity
    orders.append({
        'item': item_name,
        'quantity': quantity,
        'price': price * quantity,  # Total price for the order
        'ordered_by': session['username'],
        'order_date': datetime.now().strftime('%Y-%m-%d')
    })
    save_data(INVENTORY_FILE, inventory)
    save_data(ORDERS_FILE, orders)
    
    orders_html = ''.join([f"<tr><td>{order['item']}</td><td>{order['quantity']}</td><td>₱{order['price']:.2f}</td><td>{order['ordered_by']}</td><td>{order['order_date']}</td></tr>" for order in orders])
    item_names_html = '<option value="" disabled selected>Select Item</option>' + ''.join([f"<option value='{item['name']}' data-quantity='{item['quantity']}'>{item['name']} (Stock: {item['quantity']})</option>" for item in inventory])
    total_revenue = sum(order['price'] for order in orders)
    return jsonify({'orders': orders_html, 'item_names': item_names_html, 'total_revenue': f"{total_revenue:.2f}"})

# Export Routes
@app.route('/export_tasks')
def export_tasks():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    tasks = load_data(TASKS_FILE)
    completed_tasks = load_data(COMPLETED_TASKS_FILE)
    all_tasks = tasks + completed_tasks
    
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['Time', 'Date', 'Description', 'Status', 'Completed At'])
    for task in all_tasks:
        writer.writerow([task['time'], task['date'], task['description'], task.get('status', 'pending'), task.get('completed_at', 'N/A')])
    
    output = si.getvalue()
    si.close()
    return send_file(
        StringIO(output),
        mimetype='text/csv',
        as_attachment=True,
        download_name='tasks.csv'
    )

@app.route('/export_staff_logs')
def export_staff_logs():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    staff_logs = load_data(STAFF_FILE)
    if session['role'] != 'manager':
        staff_logs = [log for log in staff_logs if log.get('name') == session['username']]
    
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['Name', 'Time In', 'Time Out'])
    for log in staff_logs:
        writer.writerow([log['name'], log['time_in'] or 'N/A', log['time_out'] or 'N/A'])
    
    output = si.getvalue()
    si.close()
    return send_file(
        StringIO(output),
        mimetype='text/csv',
        as_attachment=True,
        download_name='staff_logs.csv'
    )

@app.route('/export_payroll')
def export_payroll():
    if 'username' not in session or session['role'] != 'manager':
        return redirect(url_for('login'))
    
    payroll_data = load_data(PAYROLL_FILE)
    
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['Name', 'Amount', 'Date'])
    for pay in payroll_data:
        writer.writerow([pay['name'], pay['amount'], pay['date']])
    
    output = si.getvalue()
    si.close()
    return send_file(
        StringIO(output),
        mimetype='text/csv',
        as_attachment=True,
        download_name='payroll.csv'
    )

@app.route('/export_inventory')
def export_inventory():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    inventory = load_data(INVENTORY_FILE)
    
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['Name', 'Quantity', 'Added By', 'Added Date'])
    for item in inventory:
        writer.writerow([item['name'], item['quantity'], item['added_by'], item['added_date']])
    
    output = si.getvalue()
    si.close()
    return send_file(
        StringIO(output),
        mimetype='text/csv',
        as_attachment=True,
        download_name='inventory.csv'
    )

@app.route('/export_borrow_history')
def export_borrow_history():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    borrow_history = load_data(BORROW_FILE)
    
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['Item', 'Quantity', 'Borrowed By', 'Borrow Date', 'Returned', 'Return Date'])
    for borrow in borrow_history:
        writer.writerow([borrow['item'], borrow['quantity'], borrow['borrowed_by'], borrow['borrow_date'], 'Yes' if borrow['returned'] else 'No', borrow.get('return_date', 'N/A')])
    
    output = si.getvalue()
    si.close()
    return send_file(
        StringIO(output),
        mimetype='text/csv',
        as_attachment=True,
        download_name='borrow_history.csv'
    )

@app.route('/export_orders')
def export_orders():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    orders = load_data(ORDERS_FILE)
    
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['Item', 'Quantity', 'Price', 'Ordered By', 'Order Date'])
    for order in orders:
        writer.writerow([order['item'], order['quantity'], order['price'], order['ordered_by'], order['order_date']])
    
    output = si.getvalue()
    si.close()
    return send_file(
        StringIO(output),
        mimetype='text/csv',
        as_attachment=True,
        download_name='orders.csv'
    )

@app.route('/logout')
def logout():
    username = session.get('username', 'unknown')
    session.pop('username', None)
    session.pop('role', None)
    logging.info(f"User {username} logged out")
    return redirect(url_for('login'))

if __name__ == '__main__':
    logging.info("Starting Store Tracker and Management System")
    app.run(debug=True, host='127.0.0.1', port=5000)