import cloudinary
import cloudinary.uploader
import logging
logging.basicConfig(level=logging.INFO)
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify
import pandas as pd
from flask import send_file
from flask import session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from flask_login import (
    LoginManager, UserMixin,
    login_user, login_required,
    logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import qrcode
import os
cloudinary.config(
    cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
    api_key=os.environ.get("CLOUDINARY_API_KEY"),
    api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
    secure=True
)
import uuid

# -------------------------
# APP CONFIG
# -------------------------

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY","dev-secret")

database_url = os.environ.get("DATABASE_URL")

if not database_url:
    # fallback for local dev
    database_url = "sqlite:///local.db"

if database_url.startswith("postgres://"):
    database_url = database_url.replace(
        "postgres://", "postgresql://", 1
    )

app.config["SQLALCHEMY_DATABASE_URI"] = database_url

app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax"
)
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.init_app(app)
login_manager.login_view = "login"

# -------------------------
# DATABASE MODELS
# -------------------------

class Student(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    admission_number = db.Column(db.String(50), unique=True, nullable=True)
    password = db.Column(db.String(200))
    role = db.Column(db.String(20))  # admin / student
    join_date = db.Column(db.String(20), default=str(datetime.today().date()))

    is_active = db.Column(db.Boolean, default=True)  # ✅ ONLY ONCE

    photo = db.Column(db.String(200))
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    address = db.Column(db.String(300))

    timing_from = db.Column(db.String(10))   # 06:00
    timing_to = db.Column(db.String(10))     # 13:00
    seat_number = db.Column(db.String(20))
    monthly_fee = db.Column(db.Integer, default=0)
    # 🔥 STRIKE SYSTEM
    current_strike = db.Column(db.Integer, default=0)
    last_present_date = db.Column(db.Date, nullable=True)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'))
    date = db.Column(db.Date)  # DATE  TYPE, not string
    check_in = db.Column(db.String(20))
    check_out = db.Column(db.String(20))
    total_hours = db.Column(db.Float)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text)
    date = db.Column(db.String(50), default=str(datetime.now()))
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=True)
    read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class QRCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    qr_token = db.Column(db.String(200))
    active = db.Column(db.Boolean, default=True)

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'))
    subject = db.Column(db.String(200))
    message = db.Column(db.Text)
    reply = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False) 
    date = db.Column(db.String(50), default=str(datetime.now()))

# ✅ FEE MODEL (CORRECTED)
class Fee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)

    amount = db.Column(db.Integer, nullable=False)   # actual paid money

    paid_month = db.Column(db.Integer, nullable=False)   # 1–12
    paid_year = db.Column(db.Integer, nullable=False)    # 2026
    paid_on = db.Column(db.Date, default=datetime.utcnow)

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(100))
    title = db.Column(db.String(200))
    amount = db.Column(db.Integer)
    payment_mode = db.Column(db.String(50))
    paid_to = db.Column(db.String(100))
    notes = db.Column(db.Text)
    date = db.Column(db.Date,index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SocialLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))      # Facebook, Instagram
    icon = db.Column(db.String(50))      # emoji ya icon class
    url = db.Column(db.String(300))      # link
    is_active = db.Column(db.Boolean, default=True)
    
# -------------------------
# LOGIN MANAGER
# -------------------------
    
@login_manager.user_loader
def load_user(user_id):
    return Student.query.get(int(user_id))

# -------------------------
# DEFAULT ADMIN
# -------------------------

def create_default_admin():
    admin = Student.query.filter_by(role="admin").first()
    print("ADMIN FOUND:", admin)

    if not admin:
        admin = Student(
            admission_number="admin",   # ✅ FIXED
            name="Administrator",
            password=generate_password_hash("admin123"),
            role="admin",
            is_active=True
        )
        db.session.add(admin)
        db.session.commit()
        print("✅ DEFAULT ADMIN CREATED")

def get_student_fee_summary(student_id):
    payments = Fee.query.filter_by(student_id=student_id).all()

    total_paid = sum(p.amount for p in payments)

    last_payment = None
    if payments:
        last_payment = max(
            payments,
            key=lambda x: (x.paid_year, x.paid_month)
        )

    return total_paid, last_payment
    
def upload_image_to_cloudinary(file):
    result = cloudinary.uploader.upload(
        file,
        folder="students",
        resource_type="image",
        transformation=[
            {"width": 800, "height": 800, "crop": "limit"},
            {"quality": "auto"},
            {"fetch_format": "auto"}
        ]
    )
    return result["secure_url"]
# -------------------------
# AUTH ROUTES
# -------------------------

@app.route("/")
def home():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        admission_number = request.form.get("admission_number")
        password = request.form.get("password")
        user = Student.query.filter_by(admission_number=admission_number).first()
        if user and check_password_hash(user.password, password):
            if not user.is_active:
                flash("Your account is blocked by admin")
                return redirect(url_for("login"))
            login_user(user, remember=True)
            return redirect(url_for(f"{user.role}_dashboard"))
        flash("Invalid Credentials")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# -------------------------
# ADMIN REGISTER STUDENT
# -------------------------

@app.route("/admin/register", methods=["GET", "POST"])
@login_required
def admin_register():
    if current_user.role != "admin":
        flash("Only admin can register students", "danger")
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        address = request.form.get("address")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        # 🔐 PASSWORD CHECK
        if password != confirm_password:
            flash("Passwords do not match!", "danger")
            return redirect(url_for("admin_register"))

        # 📞 PHONE CHECK
        if phone and (not phone.isdigit() or len(phone) != 10):
            flash("❌ Phone number must be exactly 10 digits", "danger")
            return redirect(url_for("admin_register"))

        # 📧 EMAIL DUPLICATE
        if email:
            if Student.query.filter_by(email=email).first():
                flash("❌ Email already exists!", "danger")
                return redirect(url_for("admin_register"))

        # 📸 PHOTO UPLOAD + COMPRESS (FIXED)
        photo_url = None
        photo = request.files.get("photo")

        if photo and photo.filename:
            photo_url = upload_image_to_cloudinary(photo)

        # ✅ CREATE STUDENT (OLD CODE SAFE)
        student = Student(
            name=name,
            email=email,
            phone=phone,
            address=address,
            password=generate_password_hash(password),
            role="student",
            is_active=True,
            timing_from=request.form.get("timing_from"),
            timing_to=request.form.get("timing_to"),
            monthly_fee=int(request.form.get("monthly_fee") or 0),
            seat_number=request.form.get("seat_number") or "",
            photo=photo_url
        )

        try:
            db.session.add(student)
            db.session.commit()

            student.admission_number = str(student.id)
            db.session.commit()

            flash(
                f"✅ Student registered successfully! Admission No: {student.admission_number}",
                "success"
            )
            return redirect(url_for("manage_students"))

        except Exception as e:
            db.session.rollback()
            print(e)
            flash("❌ Error while registering student!", "danger")
            return redirect(url_for("admin_register"))

    return render_template("admin_register.html")
@app.context_processor
def inject_unread_count():
    if current_user.is_authenticated and current_user.role == "admin":
        count = Ticket.query.filter_by(is_read=False).count()
        return dict(unread_count=count)
    return dict(unread_count=0)

@app.before_request
def make_session_permanent():
    session.permanent = True
# -------------------------
# ADMIN EDIT STUDENT PROFILE
# -------------------------

from datetime import datetime
import calendar
from sqlalchemy import func

def get_fee_status(student_id):

    today = datetime.today().date()
    current_month = today.month
    current_year = today.year

    student = Student.query.get(student_id)
    if not student:
        return "unpaid", 0, 0, 0, None

    monthly_fee = student.monthly_fee or 0

    # 🔹 first ever payment (joining reference)
    first_fee = Fee.query.filter_by(student_id=student_id)\
        .order_by(Fee.paid_year, Fee.paid_month)\
        .first()

    if not first_fee:
        return "unpaid", 0, monthly_fee, 0, None

    start_month = first_fee.paid_month
    start_year = first_fee.paid_year

    # 🔹 months from joining till current month (inclusive)
    expected_months = (
        (current_year - start_year) * 12 +
        (current_month - start_month) + 1
    )

    if expected_months < 1:
        expected_months = 1

    expected_total = expected_months * monthly_fee

    # 🔹 TOTAL PAID (ALL TIME)
    total_paid = db.session.query(
        func.sum(Fee.amount)
    ).filter(
        Fee.student_id == student_id
    ).scalar() or 0

    # 🔹 days left
    last_day = calendar.monthrange(current_year, current_month)[1]
    last_date = datetime(current_year, current_month, last_day).date()
    days_left = (last_date - today).days

    # ❌ DUE
    if total_paid < expected_total:
        return (
            "due",
            days_left,
            expected_total - total_paid,
            total_paid,
            None
        )

    # 💙 ADVANCE
    if total_paid > expected_total:
        advance_amount = total_paid - expected_total
        advance_months = advance_amount // monthly_fee

        return (
            "advance",
            days_left,
            0,
            total_paid,
            f"{advance_months} month advance (₹{advance_amount})"
        )

    # ✅ EXACT PAID
    return "paid", days_left, 0, total_paid, None

from datetime import timedelta

def update_strike(student, today):

    if student.last_present_date is None:
        student.current_strike = 1

    elif student.last_present_date == today - timedelta(days=1):
        student.current_strike += 1

    elif student.last_present_date == today:
        pass

    else:
        student.current_strike = 1

    student.last_present_date = today

# -------------------------
# DASHBOARDS
# -------------------------

from calendar import monthrange
from datetime import date, timedelta

@app.route("/student_dashboard")
@login_required
def student_dashboard():

    today = date.today()

    # ================= TOTAL HOURS =================
    total_hours = db.session.query(
        db.func.sum(Attendance.total_hours)
    ).filter(
        Attendance.student_id == current_user.id
    ).scalar() or 0

    # ================= TOTAL DAYS =================
    total_days = Attendance.query.filter_by(
        student_id=current_user.id
    ).count()

    # ================= TODAY HOURS =================
    today_record = Attendance.query.filter_by(
        student_id=current_user.id,
        date=today
    ).first()

    today_hours = today_record.total_hours or 0 if today_record else 0

    # ================= NOTIFICATIONS =================
    unread_count = Notification.query.filter(
        (Notification.student_id == current_user.id) |
        (Notification.student_id == None),
        Notification.read == False
    ).count()

    # ================= FEE STATUS =================
    status, days_left, due, paid, advance_month = get_fee_status(current_user.id)

    # ================= WEEKLY GRAPH =================
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    week_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    week_hours = [0, 0, 0, 0, 0, 0, 0]

    week_records = Attendance.query.filter(
        Attendance.student_id == current_user.id,
        Attendance.date >= week_start,
        Attendance.date <= week_end
    ).all()

    for r in week_records:
        if r.date:
          index = r.date.weekday()
          hours = float(r.total_hours or 0)
          week_hours[index] += round(hours, 1)

    # ================= MONTHLY CALENDAR =================
    month_start = today.replace(day=1)
    month_end = today.replace(
        day=monthrange(today.year, today.month)[1]
    )

    month_days = [
        month_start + timedelta(days=i)
        for i in range((month_end - month_start).days + 1)
    ]

    attendance_records = Attendance.query.filter(
        Attendance.student_id == current_user.id,
        Attendance.date >= month_start,
        Attendance.date <= month_end
    ).all()

    attendance_dict = {}

    for record in attendance_records:
        if record.date:
            date_key = record.date.strftime("%Y-%m-%d")

            if record.check_in:
                attendance_dict[date_key] = "present"
            else:
                attendance_dict[date_key] = "absent"

    # ================= SEND TO TEMPLATE =================
    return render_template(
        "student_dashboard.html",
        student=current_user,
        total_hours=round(total_hours, 2),
        total_days=total_days,
        today_hours=round(today_hours, 2),
        unread_count=unread_count,
        fee_status=status,
        remaining_days=days_left,
        due_amount=due,
        paid_amount=paid,
        advance_month=advance_month,
        # Weekly Graph
        graph_labels=week_labels,
        graph_hours=week_hours,

        # Monthly Calendar
        month_days=month_days,
        attendance_dict=attendance_dict
    )


@app.route("/admin_dashboard", methods=["GET"])
@login_required
def admin_dashboard():

    if current_user.role != "admin":
        return redirect(url_for("student_dashboard"))

    # 🔹 total students
    total_students = Student.query.filter_by(role="student").count()

    # 🔹 today attendance count
    today = datetime.today().date()
    today_attendance = Attendance.query.filter_by(date=today).count()

    # 🔹 active QR
    qr = QRCode.query.filter_by(active=True).first()

    # 🔍 SEARCH BY ADMISSION NUMBER (GET)
    search_admission = request.args.get("admission_number")

    # 🔹 all students (for fee section)
    query = Student.query.filter_by(role="student")

    if search_admission:
        query = query.filter(
            Student.admission_number.contains(search_admission)
        )

    students = query.all()

    # 🔥 UNPAID / DUE / ADVANCE / PAID ORDER
    def fee_priority(student):
        status = get_fee_status(student.id)[0]

        if status == "unpaid":
            return 0   # ❌ fee not paid → sabse upar
        elif status == "due":
            return 1   # ⚠ partial / due
        elif status == "advance":
            return 2   # 💙 advance
        else:
            return 3   # ✅ paid → last

    students.sort(key=fee_priority)

    # ==================================================
    # 🔥🔥🔥 EXPENSE SUMMARY (ADDED – PRO LEVEL)
    # ==================================================

    # 🔥 TODAY EXPENSE (SAFE)
    today_expense = db.session.query(
        db.func.sum(Expense.amount)
    ).filter(
        Expense.date == datetime.today().date()
    ).scalar() or 0

    # 🔥 THIS MONTH EXPENSE (FIXED)
    month_expense = db.session.query(
        db.func.sum(Expense.amount)
    ).filter(
        Expense.date >= datetime.today().replace(day=1).date(),
        Expense.date <= datetime.today().date()
    ).scalar() or 0

    # 📊 Total Expense (All Time)
    total_expense = db.session.query(
        db.func.sum(Expense.amount)
    ).scalar() or 0
    # ==================================================
    # 🔔🔔🔔 SUPPORT NOTIFICATION (NEW – ADDED)
    # ==================================================

    unread_count = Ticket.query.filter_by(is_read=False).count()

    
    # ==================================================

    return render_template(
        "admin_dashboard.html",
        total_students=total_students,
        today_attendance=today_attendance,
        qr=qr,
        students=students,
        get_fee_status=get_fee_status,

        # 🔥 PASS EXPENSE DATA (NEW)
        today_expense=today_expense,
        month_expense=month_expense,
        total_expense=total_expense,
        unread_count=unread_count
    )

@app.context_processor
def inject_social_links():
    links = SocialLink.query.filter_by(is_active=True).all()
    return dict(social_links=links)

@app.route("/admin/today-attendance")
@login_required
def today_attendance():
    if current_user.role != "admin":
        return redirect(url_for("scan"))

    today = datetime.today().date()

    records = db.session.query(
        Attendance,
        Student
    ).join(
        Student, Attendance.student_id == Student.id
    ).filter(
        Attendance.date == today
    ).all()

    return render_template(
        "admin_today_attendance.html",
        records=records,
        today=today
    )
# -------------------------
# STUDENT MANAGEMENT
# -------------------------

@app.route("/admin/students")
@login_required
def manage_students():
    if current_user.role != "admin":
        return redirect(url_for("student_dashboard"))
    students = Student.query.filter_by(role="student").all()
    return render_template("manage_students.html", students=students)

@app.route("/admin/toggle_student/<int:id>")
@login_required
def toggle_student(id):
    if current_user.role != "admin":
        return redirect(url_for("admin_dashboard"))
    student = Student.query.get_or_404(id)
    student.is_active = not student.is_active
    db.session.commit()
    return redirect(url_for("manage_students"))

@app.route("/admin/delete_student/<int:id>")
@login_required
def delete_student(id):
    if current_user.role != "admin":
        return redirect(url_for("admin_dashboard"))
    student = Student.query.get_or_404(id)
    db.session.delete(student)
    db.session.commit()
    return redirect(url_for("manage_students"))

@app.route("/admin/reset_password/<int:id>", methods=["GET","POST"])
@login_required
def reset_password(id):
    if current_user.role != "admin":
        flash("Access Denied")
        return redirect(url_for("login"))
    student = Student.query.get_or_404(id)
    if request.method == "POST":
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")
        if new_password != confirm_password:
            flash("Passwords do not match!")
            return redirect(url_for("reset_password", id=id))
        student.password = generate_password_hash(new_password)
        db.session.commit()
        flash("Password updated successfully!")
        return redirect(url_for("manage_students"))
    return render_template("reset_password.html", student=student)

# -------------------------
# NOTIFICATIONS
# -------------------------

@app.route("/send_notification", methods=["GET","POST"])
@login_required
def send_notification():
    if current_user.role != "admin":
        return redirect(url_for("student_dashboard"))
    if request.method == "POST":
        message = request.form.get("message")
        notification = Notification(message=message, student_id=None)
        db.session.add(notification)
        db.session.commit()
        flash("Notification Sent Successfully!")
        return redirect(url_for("admin_dashboard"))
    return render_template("send_notification.html")

@app.route("/notifications")
@login_required
def notifications():
    notifications = Notification.query.filter(
        (Notification.student_id == current_user.id) | (Notification.student_id == None)
    ).order_by(Notification.date.desc()).all()
    for n in notifications:
        n.read = True
    db.session.commit()
    return render_template("notifications.html", notifications=notifications)

# -------------------------
# SUPPORT TICKETS
# -------------------------

@app.route("/support", methods=["GET","POST"])
@login_required
def support():
    if request.method == "POST":
        subject = request.form.get("subject")
        message = request.form.get("message")
        ticket = Ticket(
            student_id=current_user.id,
            subject=subject,
            message=message,
            date=str(datetime.today().date())
        )
        db.session.add(ticket)
        db.session.commit()
        flash("Support ticket submitted successfully!")
        return redirect(url_for("support"))
    tickets = Ticket.query.filter_by(student_id=current_user.id).order_by(Ticket.date.desc()).all()
    return render_template("support.html", tickets=tickets)

@app.route("/admin/support", methods=["GET","POST"])
@login_required
def admin_support():
    if current_user.role != "admin":
        return redirect(url_for("student_dashboard"))
    if request.method == "POST":
        ticket_id = request.form.get("ticket_id")
        reply = request.form.get("reply")
        ticket = Ticket.query.get(ticket_id)
        if ticket:
            ticket.reply = reply
            db.session.commit()
            flash("Reply sent successfully!")
        return redirect(url_for("admin_support"))
    tickets = Ticket.query.order_by(Ticket.date.desc()).all()
    return render_template("admin_support.html", tickets=tickets)



# -------------------------
# PROFILE
# -------------------------
@app.route("/admin/student/<int:student_id>", methods=["GET", "POST"])
@login_required
def admin_view_student_profile(student_id):

    # ================= ADMIN CHECK =================
    if current_user.role != "admin":
        flash("Unauthorized access")
        return redirect(url_for("admin_dashboard"))

    # ================= STUDENT FETCH =================
    student = db.session.get(Student, student_id)

    if not student:
        flash("Student not found")
        return redirect(url_for("manage_students"))

    # ================= FEE SUMMARY =================
    total_paid, last_payment = get_student_fee_summary(student.id)

    # ================= POST: ADMIN EDIT =================
    if request.method == "POST":

        # editable fields
        student.email = request.form.get("email")
        student.phone = request.form.get("phone")
        student.address = request.form.get("address")
        # 🔹 Joining Date (ADMIN ONLY)
        join_date = request.form.get("join_date")
        if join_date:
            student.join_date = join_date
        # seat & timing
        student.seat_number = request.form.get("seat_number")
        student.timing_from = request.form.get("timing_from")
        student.timing_to = request.form.get("timing_to")

        student.is_active = True if request.form.get("is_active") == "1" else False

        # photo update
        photo = request.files.get("photo")
        if photo and photo.filename:
            student.photo = upload_image_to_cloudinary(photo)

        db.session.commit()
        flash("Student profile updated successfully")
        # ✅ FIXED redirect
        return redirect(
            url_for("admin_view_student_profile", student_id=student.id)
        )

    # ================= RENDER =================
    return render_template(
        "profile.html",
        student=student,
        total_paid=total_paid,
        last_payment=last_payment,
        admin_view=True
    )

# -------------------------
# QR CODE
# -------------------------

@app.route("/generate_qr")
@login_required
def generate_qr():
    if current_user.role != "admin":
        return redirect(url_for("student_dashboard"))
    QRCode.query.update({"active": False})
    db.session.commit()
    token = str(uuid.uuid4())
    qr = QRCode(qr_token=token, active=True)
    db.session.add(qr)
    db.session.commit()
    os.makedirs("static/qr_codes", exist_ok=True)
    img = qrcode.make(token)
    img.save("static/qr_codes/permanent_qr.png")
    return redirect(url_for("admin_dashboard"))

@app.route("/scan", methods=["GET","POST"])
@login_required
def scan():
    if request.method == "GET":
        if current_user.role != "student":
            return redirect(url_for("admin_dashboard"))
        return render_template("scan.html")

    token = request.json.get("token")
    qr = QRCode.query.filter_by(qr_token=token, active=True).first()
    if not qr:
        return jsonify({"message": "Invalid QR Code"})

    today = datetime.today().date()   # ✅ DATE object
    now = datetime.now()

    record = Attendance.query.filter_by(
        student_id=current_user.id,
        date=today
    ).first()

    if not record:
        record = Attendance(
            student_id=current_user.id,
            date=today,
            check_in=now.strftime("%H:%M:%S")
        )
        db.session.add(record)
        update_strike(current_user, today)
        db.session.commit()
        return jsonify({"message": "Check-in Successful"})

    if not record.check_out:
        check_in_time = datetime.strptime(record.check_in, "%H:%M:%S")
        record.check_out = now.strftime("%H:%M:%S")
        record.total_hours = round((now - check_in_time).seconds / 3600, 2)
        db.session.commit()
        return jsonify({"message": "Check-out Successful"})

    return jsonify({"message": "Already Checked Out Today"})
# -------------------------
# LEADERBOARD
# -------------------------

@app.route("/leaderboard")
@login_required
def leaderboard():
    raw = db.session.query(
        Student.name,
        db.func.sum(Attendance.total_hours),
        db.func.count(Attendance.id)
    ).outerjoin(Attendance, Student.id == Attendance.student_id)\
     .group_by(Student.id).all()
    results = []
    for name, hours, days in raw:
        hours = hours or 0
        results.append({"name": name, "total_hours": round(hours,2), "total_days": days, "progress": min(hours*5,100)})
    results.sort(key=lambda x: (x["total_hours"], x["total_days"]), reverse=True)
    return render_template("leaderboard.html", results=results)


from datetime import datetime

@app.route("/mark_fee/<int:student_id>", methods=["POST"])
@login_required
def mark_fee(student_id):

    month = int(request.form.get("month"))
    year = int(request.form.get("year"))
    amount = int(request.form.get("amount") or 0)

    if amount <= 0:
        flash("❌ Invalid fee amount", "danger")
        return redirect(url_for("admin_dashboard"))

    student = Student.query.get_or_404(student_id)

    # 🔍 same student + same month + same year
    fee = Fee.query.filter_by(
        student_id=student_id,
        paid_month=month,
        paid_year=year
    ).first()

    if fee:
        # ✅ ADD amount (partial / remaining / extra)
        fee.amount += amount
    else:
        # 🆕 create new entry (future / first payment)
        fee = Fee(
            student_id=student_id,
            amount=amount,
            paid_month=month,
            paid_year=year,
            paid_on=datetime.today().date()
        )
        db.session.add(fee)

    db.session.commit()

    flash("✅ Fee recorded successfully", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/student-details", methods=["GET", "POST"])
@login_required
def student_details():

    if current_user.role != "admin":
        return redirect(url_for("student_dashboard"))

    student = None
    total_paid = 0
    last_payment = None

    # 👇 page load pe sab students
    students = Student.query.filter_by(role="student").all()

    if request.method == "POST":
        admission_number = request.form.get("admission_number")

        student = Student.query.filter_by(
            admission_number=admission_number
        ).first()

        if student:
            total_paid, last_payment = get_student_fee_summary(student.id)

    return render_template(
        "student_details.html",
        student=student,
        students=students,
        total_paid=total_paid,
        last_payment=last_payment
    )

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    student = current_user

    if request.method == "POST":

        # 📸 PHOTO UPDATE (RESIZE + COMPRESS ≤200KB)
        photo = request.files.get("photo")
        if photo and photo.filename:

            # 🔴 ADD: OLD PHOTO DELETE (AUTO CLEAN)
            if student.photo:
                photo = request.files.get("photo")
                if photo and photo.filename:
                    student.photo = upload_image_to_cloudinary(photo)

        # 🔐 ADMIN EXTRA CONTROLS (UNCHANGED)
        if current_user.role == "admin":
            student.email = request.form.get("email")
            student.phone = request.form.get("phone")
            student.address = request.form.get("address")
            student.seat_number = request.form.get("seat_number")
            student.timing_from = request.form.get("timing_from")
            student.timing_to = request.form.get("timing_to")
            student.is_active = bool(int(request.form.get("is_active")))
            student.join_date = request.form.get("join_date")

        db.session.commit()
        flash("✅ Profile updated successfully", "success")

    total_paid, last_payment = get_student_fee_summary(student.id)

    return render_template(
        "profile.html",
        student=student,
        total_paid=total_paid,
        last_payment=last_payment,
        admin_view=False
    )

@app.route("/add-expense", methods=["GET", "POST"])
@login_required
def add_expense():

    if current_user.role != "admin":
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        expense = Expense(
            category=request.form["category"],
            title=request.form["title"],
            amount=int(request.form["amount"]),
            payment_mode=request.form["payment"],
            paid_to=request.form["paid_to"],
            notes=request.form["notes"],
            date=datetime.strptime(request.form["date"], "%Y-%m-%d").date()
        )
        db.session.add(expense)
        db.session.commit()
        flash("✅ Expense Added Successfully", "success")
        return redirect(url_for("expense_list"))

    return render_template("add_expense.html")

@app.route("/admin/expenses")
@login_required
def expense_list():

    if current_user.role != "admin":
        return redirect(url_for("student_dashboard"))

    month = request.args.get("month")
    year = request.args.get("year")

    query = Expense.query

    if month and year:
        query = query.filter(
            db.extract("month", Expense.date) == int(month),
            db.extract("year", Expense.date) == int(year)
        )

    expenses = query.order_by(Expense.date.desc()).all()

    total_expense = sum(e.amount for e in expenses)

    return render_template(
        "expense_list.html",
        expenses=expenses,
        total_expense=total_expense
    )

@app.route("/admin/expenses/export/excel")
@login_required
def export_expenses_excel():

    expenses = Expense.query.order_by(Expense.date.desc()).limit(100).all()

    data = [{
        "Date": e.date,
        "Category": e.category,
        "Title": e.title,
        "Amount": e.amount,
        "Payment": e.payment_mode
    } for e in expenses]

    df = pd.DataFrame(data)

    file = "expenses.xlsx"
    df.to_excel(file, index=False)

    return send_file(file, as_attachment=True)

@app.route("/admin/social-links", methods=["GET","POST"])
@login_required
def manage_social_links():

    if current_user.role != "admin":
        return redirect(url_for("student_dashboard"))

    if request.method == "POST":
        link = SocialLink(
            name=request.form["name"],
            icon=request.form["icon"],
            url=request.form["url"]
        )
        db.session.add(link)
        db.session.commit()
        flash("✅ Social link added")
        return redirect(url_for("manage_social_links"))

    links = SocialLink.query.all()
    return render_template("admin_social_links.html", links=links)
@app.route("/admin/clear-bell", methods=["POST"])
@login_required
def clear_bell():
    Ticket.query.filter_by(is_read=False)\
        .update({Ticket.is_read: True})
    db.session.commit()
    return "", 204
@app.route("/admin/seats")
@login_required
def admin_seats():

    # 🔐 Only admin allowed
    if current_user.role != "admin":
        return redirect(url_for("student_dashboard"))

    # 🪑 Only students jinhone seat li hai
    students = Student.query.filter(
        Student.seat_number != None,
        Student.seat_number != ""
    ).order_by(Student.seat_number).all()

    return render_template(
        "admin_seats.html",
        students=students
    )
# -------------------------
# DB INIT (FIRST DEPLOY ONLY)
# -------------------------
with app.app_context():
        db.create_all()
        create_default_admin()


# -------------------------
# RUN APP
# -------------------------
import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)








