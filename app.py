from flask import Flask, render_template, request, redirect, session, send_file
from flask_mysqldb import MySQL
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.platypus import SimpleDocTemplate, Table
from openpyxl import Workbook

import MySQLdb.cursors
import google.generativeai as genai
import os
import io
import config


# APP CONFIGURATION

app = Flask(__name__)

app.config["MYSQL_HOST"] = config.MYSQL_HOST
app.config["MYSQL_USER"] = config.MYSQL_USER
app.config["MYSQL_PASSWORD"] = config.MYSQL_PASSWORD
app.config["MYSQL_DB"] = config.MYSQL_DB

app.secret_key = config.SECRET_KEY


# UPLOAD FOLDER

UPLOAD_FOLDER = "static/uploads"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# MYSQL

mysql = MySQL(app)


# GEMINI AI

model = None

if config.GEMINI_API_KEY:

    genai.configure(
        api_key=config.GEMINI_API_KEY
    )

    model = genai.GenerativeModel(
        "gemini-1.5-flash"
    )


# AUTHENTICATION

@app.route("/", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        cursor = mysql.connection.cursor(
            MySQLdb.cursors.DictCursor
        )

        cursor.execute(
            "SELECT * FROM users WHERE email=%s",
            (email,)
        )

        user = cursor.fetchone()

        cursor.close()

        # Password check
        if user and check_password_hash(
            user["password"],
            password
        ):

            # Voter approval check
            if (
                user["role"] == "voter"
                and user["status"] != "Approved"
            ):

                return render_template(
                    "login.html",
                    error="Your account is pending admin approval."
                )

            # Session
            session["loggedin"] = True
            session["id"] = user["id"]
            session["name"] = user["full_name"]
            session["role"] = user["role"]

            # Redirect
            if user["role"] == "admin":
                return redirect("/admin")

            return redirect("/voter")

        return render_template(
            "login.html",
            error="Invalid email or password."
        )

    return render_template("login.html")


# REGISTER

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        full_name = request.form["full_name"]
        email = request.form["email"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        # Password confirmation
        if password != confirm_password:

            return render_template(
                "register.html",
                error="Passwords do not match."
            )

        cursor = mysql.connection.cursor(
            MySQLdb.cursors.DictCursor
        )

        # Check email
        cursor.execute(
            "SELECT id FROM users WHERE email=%s",
            (email,)
        )

        existing_user = cursor.fetchone()

        if existing_user:

            cursor.close()

            return render_template(
                "register.html",
                error="Email already registered."
            )

        # Hash password
        hashed_password = generate_password_hash(
            password
        )

        cursor.execute(
            """
            INSERT INTO users
            (full_name, email, password, role, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                full_name,
                email,
                hashed_password,
                "voter",
                "Pending"
            )
        )

        mysql.connection.commit()

        cursor.close()

        return redirect("/")

    return render_template("register.html")


# LOGOUT

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


# ADMIN DASHBOARD

@app.route("/admin")
def admin():

    if (
        "loggedin" in session
        and session["role"] == "admin"
    ):

        return render_template(
            "admin_dashboard.html"
        )

    return redirect("/")


# VOTERS - ADMIN

@app.route("/voter")
def voter():

    # ================= LOGIN CHECK =================

    if "loggedin" not in session or session.get("role") != "voter":
        return redirect("/")


    cursor = mysql.connection.cursor(
        MySQLdb.cursors.DictCursor
    )

    voter_id = session["id"]


    # ================= USER =================

    cursor.execute(
        """
        SELECT *
        FROM users
        WHERE id=%s
        """,
        (voter_id,)
    )

    user = cursor.fetchone()


    # ================= ACTIVE ELECTIONS =================

    cursor.execute(
        """
        SELECT *
        FROM elections
        WHERE status=%s
        ORDER BY start_date ASC
        """,
        ("Active",)
    )

    elections = cursor.fetchall()


    # ================= CANDIDATES =================

    total_candidates = 0

    for election in elections:

        cursor.execute(
            """
            SELECT *
            FROM candidates
            WHERE election_id=%s
            AND (status=%s OR status=%s)
            ORDER BY id ASC
            """,
            (
                election["id"],
                "active",
                "Active"
            )
        )

        candidates = cursor.fetchall()

        # Candidates ko election ke andar attach karo
        election["candidates"] = candidates

        total_candidates += len(candidates)


    # ================= ACTIVE ELECTION COUNT =================

    total_active_elections = len(elections)


    # ================= VOTED ELECTIONS =================

    cursor.execute(
        """
        SELECT DISTINCT election_id
        FROM votes
        WHERE voter_id=%s
        """,
        (voter_id,)
    )

    voted_rows = cursor.fetchall()


    voted_election_ids = [
        row["election_id"]
        for row in voted_rows
    ]


    # ================= HAS VOTED =================

    has_voted = len(voted_election_ids) > 0


    # ================= NOTIFICATIONS =================

    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM notifications
        WHERE (user_id IS NULL OR user_id=%s)
        AND is_read=0
        """,
        (voter_id,)
    )

    notification_result = cursor.fetchone()

    notification_count = (
        notification_result["total"]
        if notification_result
        else 0
    )


    cursor.close()


    # ================= DASHBOARD =================

    return render_template(
        "voter_dashboard.html",

        user=user,

        elections=elections,

        total_active_elections=total_active_elections,

        total_candidates=total_candidates,

        voted_election_ids=voted_election_ids,

        has_voted=has_voted,

        notification_count=notification_count
    )

# CANDIDATES

@app.route("/candidates")
def candidates():

    if (
        "loggedin" not in session
        or session["role"] != "admin"
    ):

        return redirect("/")

    cursor = mysql.connection.cursor(
        MySQLdb.cursors.DictCursor
    )

    cursor.execute(
        "SELECT * FROM candidates"
    )

    data = cursor.fetchall()

    cursor.close()

    return render_template(
        "candidates.html",
        candidates=data
    )


# ADD CANDIDATE

@app.route("/add_candidate", methods=["GET", "POST"])
def add_candidate():

    # ================= ADMIN LOGIN CHECK =================

    if (
        "loggedin" not in session
        or session.get("role") != "admin"
    ):
        return redirect("/")


    cursor = mysql.connection.cursor(
        MySQLdb.cursors.DictCursor
    )


    # ================= GET ELECTIONS =================

    cursor.execute(
        """
        SELECT id, title, status
        FROM elections
        ORDER BY id DESC
        """
    )

    elections = cursor.fetchall()


    # ================= POST =================

    if request.method == "POST":

        full_name = request.form.get("full_name", "").strip()

        party_name = request.form.get("party_name", "").strip()

        symbol = request.form.get("symbol", "").strip()

        manifesto = request.form.get("manifesto", "").strip()

        election_id = request.form.get("election_id")


        # ================= VALIDATION =================

        if not election_id:

            cursor.close()

            return "Please select an election."


        # ================= PHOTO =================

        photo = request.files.get("photo")

        filename = ""


        if photo and photo.filename != "":

            filename = secure_filename(
                photo.filename
            )

            photo.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )
            )


        # ================= INSERT CANDIDATE =================

        cursor.execute(
            """
            INSERT INTO candidates
            (
                full_name,
                party_name,
                symbol,
                photo,
                manifesto,
                election_id,
                status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                full_name,
                party_name,
                symbol,
                filename,
                manifesto,
                election_id,
                "active"
            )
        )


        mysql.connection.commit()

        cursor.close()


        return redirect("/candidates")


    # ================= GET =================

    cursor.close()


    return render_template(
        "add_candidate.html",
        elections=elections
    )

# EDIT CANDIDATE

@app.route(
    "/edit_candidate/<int:id>",
    methods=["GET", "POST"]
)
def edit_candidate(id):

    if (
        "loggedin" not in session
        or session["role"] != "admin"
    ):

        return redirect("/")

    cursor = mysql.connection.cursor(
        MySQLdb.cursors.DictCursor
    )

    if request.method == "POST":

        full_name = request.form["full_name"]
        party_name = request.form["party_name"]
        symbol = request.form["symbol"]
        manifesto = request.form["manifesto"]
        status = request.form["status"]

        photo = request.files.get("photo")

        if photo and photo.filename != "":

            filename = secure_filename(
                photo.filename
            )

            photo.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )
            )

            cursor.execute(
                """
                UPDATE candidates
                SET
                    full_name=%s,
                    party_name=%s,
                    symbol=%s,
                    photo=%s,
                    manifesto=%s,
                    status=%s
                WHERE id=%s
                """,
                (
                    full_name,
                    party_name,
                    symbol,
                    filename,
                    manifesto,
                    status,
                    id
                )
            )

        else:

            cursor.execute(
                """
                UPDATE candidates
                SET
                    full_name=%s,
                    party_name=%s,
                    symbol=%s,
                    manifesto=%s,
                    status=%s
                WHERE id=%s
                """,
                (
                    full_name,
                    party_name,
                    symbol,
                    manifesto,
                    status,
                    id
                )
            )

        mysql.connection.commit()

        cursor.close()

        return redirect("/candidates")

    cursor.execute(
        "SELECT * FROM candidates WHERE id=%s",
        (id,)
    )

    candidate = cursor.fetchone()

    cursor.close()

    return render_template(
        "edit_candidate.html",
        candidate=candidate
    )


# DELETE CANDIDATE

@app.route("/delete_candidate/<int:id>")
def delete_candidate(id):

    if (
        "loggedin" not in session
        or session["role"] != "admin"
    ):

        return redirect("/")

    cursor = mysql.connection.cursor()

    cursor.execute(
        "DELETE FROM candidates WHERE id=%s",
        (id,)
    )

    mysql.connection.commit()

    cursor.close()

    return redirect("/candidates")


# ELECTIONS

@app.route("/elections")
def elections():

    if (
        "loggedin" not in session
        or session["role"] != "admin"
    ):

        return redirect("/")

    cursor = mysql.connection.cursor(
        MySQLdb.cursors.DictCursor
    )

    cursor.execute(
        "SELECT * FROM elections"
    )

    data = cursor.fetchall()

    cursor.close()

    return render_template(
        "elections.html",
        elections=data
    )


# ADD ELECTION

@app.route(
    "/add_election",
    methods=["GET", "POST"]
)
def add_election():

    if (
        "loggedin" not in session
        or session["role"] != "admin"
    ):

        return redirect("/")

    if request.method == "POST":

        title = request.form["title"]
        description = request.form["description"]
        start_date = request.form["start_date"]
        end_date = request.form["end_date"]

        cursor = mysql.connection.cursor()

        cursor.execute(
            """
            INSERT INTO elections
            (title, description, start_date, end_date, status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                title,
                description,
                start_date,
                end_date,
                "Upcoming"
            )
        )

        mysql.connection.commit()

        cursor.close()

        return redirect("/elections")

    return render_template(
        "add_election.html"
    )


# EDIT ELECTION

@app.route(
    "/edit_election/<int:id>",
    methods=["GET", "POST"]
)
def edit_election(id):

    if (
        "loggedin" not in session
        or session["role"] != "admin"
    ):

        return redirect("/")

    cursor = mysql.connection.cursor(
        MySQLdb.cursors.DictCursor
    )

    if request.method == "POST":

        title = request.form["title"]
        description = request.form["description"]
        start_date = request.form["start_date"]
        end_date = request.form["end_date"]
        status = request.form["status"]

        cursor.execute(
            """
            UPDATE elections
            SET
                title=%s,
                description=%s,
                start_date=%s,
                end_date=%s,
                status=%s
            WHERE id=%s
            """,
            (
                title,
                description,
                start_date,
                end_date,
                status,
                id
            )
        )

        mysql.connection.commit()

        cursor.close()

        return redirect("/elections")

    cursor.execute(
        "SELECT * FROM elections WHERE id=%s",
        (id,)
    )

    election = cursor.fetchone()

    cursor.close()

    return render_template(
        "edit_election.html",
        election=election
    )


# START ELECTION

@app.route("/start_election/<int:id>")
def start_election(id):

    if "loggedin" not in session or session["role"] != "admin":
        return redirect("/")

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Election details
    cursor.execute(
        "SELECT * FROM elections WHERE id=%s",
        (id,)
    )

    election = cursor.fetchone()

    if not election:
        cursor.close()
        return redirect("/elections")

    # Sirf selected election ko Active karo
    cursor.execute(
        """
        UPDATE elections
        SET status='Active'
        WHERE id=%s
        """,
        (id,)
    )

    # Automatic notification
    cursor.execute(
        """
        INSERT INTO notifications
        (user_id, title, message, is_read)
        VALUES
        (NULL, %s, %s, 0)
        """,
        (
            "Election Started 🟢",
            f"The election '{election['title']}' has started. You can now cast your vote."
        )
    )

    mysql.connection.commit()
    cursor.close()

    return redirect("/elections")

# END ELECTION

@app.route("/end_election/<int:id>")
def end_election(id):

    if "loggedin" not in session or session["role"] != "admin":
        return redirect("/")

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Get election details
    cursor.execute(
        """
        SELECT *
        FROM elections
        WHERE id=%s
        """,
        (id,)
    )

    election = cursor.fetchone()

    if not election:
        cursor.close()
        return redirect("/elections")

    # Complete only this election
    cursor.execute(
        """
        UPDATE elections
        SET status='Completed'
        WHERE id=%s
        """,
        (id,)
    )

    # Automatic notification
    cursor.execute(
        """
        INSERT INTO notifications
        (user_id, title, message, is_read)
        VALUES
        (NULL, %s, %s, 0)
        """,
        (
            "Election Ended 🔴",
            f"The election '{election['title']}' has ended. Voting is now closed."
        )
    )

    mysql.connection.commit()
    cursor.close()

    return redirect("/elections")

# DELETE ELECTION

@app.route("/delete_election/<int:id>")
def delete_election(id):

    if (
        "loggedin" not in session
        or session["role"] != "admin"
    ):

        return redirect("/")

    cursor = mysql.connection.cursor()

    cursor.execute(
        "DELETE FROM elections WHERE id=%s",
        (id,)
    )

    mysql.connection.commit()

    cursor.close()

    return redirect("/elections")


# VOTERS - ADMIN

@app.route("/voters")
def voters():
    if "loggedin" not in session or session["role"] != "admin":
        return redirect("/")

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    cursor.execute("SELECT * FROM users WHERE role=%s", ("voter",))
    voters = cursor.fetchall()

    cursor.close()

    return render_template("voters.html", voters=voters)


# ADD VOTER

@app.route(
    "/add_voter",
    methods=["GET", "POST"]
)
def add_voter():

    if (
        "loggedin" not in session
        or session["role"] != "admin"
    ):

        return redirect("/")

    if request.method == "POST":

        full_name = request.form["full_name"]
        email = request.form["email"]
        cnic = request.form["cnic"]
        phone = request.form["phone"]

        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        status = request.form["status"]

        if password != confirm_password:

            return render_template(
                "add_voter.html",
                error="Passwords do not match."
            )

        hashed_password = generate_password_hash(
            password
        )

        photo = request.files.get("photo")

        filename = ""

        if photo and photo.filename != "":

            filename = secure_filename(
                photo.filename
            )

            photo.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )
            )

        cursor = mysql.connection.cursor()

        cursor.execute(
            """
            INSERT INTO users
            (
                full_name,
                email,
                password,
                cnic,
                phone,
                photo,
                role,
                status
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                full_name,
                email,
                hashed_password,
                cnic,
                phone,
                filename,
                "voter",
                status
            )
        )

        mysql.connection.commit()

        cursor.close()

        return redirect("/voters")

    return render_template(
        "add_voter.html"
    )


# EDIT VOTER

@app.route(
    "/edit_voter/<int:id>",
    methods=["GET", "POST"]
)
def edit_voter(id):

    if (
        "loggedin" not in session
        or session["role"] != "admin"
    ):

        return redirect("/")

    cursor = mysql.connection.cursor(
        MySQLdb.cursors.DictCursor
    )

    if request.method == "POST":

        full_name = request.form["full_name"]
        email = request.form["email"]
        cnic = request.form["cnic"]
        phone = request.form["phone"]
        status = request.form["status"]

        photo = request.files.get("photo")

        if photo and photo.filename != "":

            filename = secure_filename(
                photo.filename
            )

            photo.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )
            )

            cursor.execute(
                """
                UPDATE users
                SET
                    full_name=%s,
                    email=%s,
                    cnic=%s,
                    phone=%s,
                    photo=%s,
                    status=%s
                WHERE id=%s
                """,
                (
                    full_name,
                    email,
                    cnic,
                    phone,
                    filename,
                    status,
                    id
                )
            )

        else:

            cursor.execute(
                """
                UPDATE users
                SET
                    full_name=%s,
                    email=%s,
                    cnic=%s,
                    phone=%s,
                    status=%s
                WHERE id=%s
                """,
                (
                    full_name,
                    email,
                    cnic,
                    phone,
                    status,
                    id
                )
            )

        mysql.connection.commit()

        cursor.close()

        return redirect("/voters")

    cursor.execute(
        "SELECT * FROM users WHERE id=%s",
        (id,)
    )

    voter_data = cursor.fetchone()

    cursor.close()

    return render_template(
        "edit_voter.html",
        voter=voter_data
    )


# APPROVE VOTER


@app.route("/approve_voter/<int:id>")
def approve_voter(id):

    if (
        "loggedin" not in session
        or session["role"] != "admin"
    ):

        return redirect("/")

    cursor = mysql.connection.cursor()

    cursor.execute(
        """
        UPDATE users
        SET status=%s
        WHERE id=%s
        """,
        (
            "Approved",
            id
        )
    )

    mysql.connection.commit()

    cursor.close()

    return redirect("/voters")


# REJECT VOTER


@app.route("/reject_voter/<int:id>")
def reject_voter(id):

    if (
        "loggedin" not in session
        or session["role"] != "admin"
    ):

        return redirect("/")

    cursor = mysql.connection.cursor()

    cursor.execute(
        """
        UPDATE users
        SET status=%s
        WHERE id=%s
        """,
        (
            "Rejected",
            id
        )
    )

    mysql.connection.commit()

    cursor.close()

    return redirect("/voters")


# DELETE VOTER

@app.route("/delete_voter/<int:id>")
def delete_voter(id):

    if (
        "loggedin" not in session
        or session["role"] != "admin"
    ):

        return redirect("/")

    cursor = mysql.connection.cursor()

    cursor.execute(
        "DELETE FROM users WHERE id=%s",
        (id,)
    )

    mysql.connection.commit()

    cursor.close()

    return redirect("/voters")


# LIVE ELECTION - VOTER

@app.route("/live_election")
def live_election():

    if (
        "loggedin" not in session
        or session["role"] != "voter"
    ):
        return redirect("/")

    cursor = mysql.connection.cursor(
        MySQLdb.cursors.DictCursor
    )

    cursor.execute("""
        SELECT *
        FROM elections
        WHERE status='Active'
        ORDER BY id DESC
    """)

    elections = cursor.fetchall()

    cursor.close()

    return render_template(
        "live_election.html",
        elections=elections
    )

# PROFILE - VOTER

@app.route("/profile")
def profile():

    if (
        "loggedin" not in session
        or session["role"] != "voter"
    ):

        return redirect("/")

    cursor = mysql.connection.cursor(
        MySQLdb.cursors.DictCursor
    )

    cursor.execute(
        """
        SELECT *
        FROM users
        WHERE id=%s
        """,
        (session["id"],)
    )

    user = cursor.fetchone()

    cursor.close()

    return render_template(
        "profile.html",
        user=user
    )

@app.route("/edit_profile", methods=["GET", "POST"])
def edit_profile():

    if "loggedin" not in session or session["role"] != "voter":
        return redirect("/")

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    cursor.execute(
        "SELECT * FROM users WHERE id=%s",
        (session["id"],)
    )

    user = cursor.fetchone()

    error = None
    success = None

    if request.method == "POST":

        full_name = request.form["full_name"]
        cnic = request.form["cnic"]
        phone = request.form["phone"]

        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]

        photo = request.files.get("photo")

        filename = user["photo"]

        # Upload new photo
        if photo and photo.filename != "":
            filename = secure_filename(photo.filename)
            photo.save(
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )
            )

        # Password validation
        if new_password != "" or confirm_password != "":

            if new_password != confirm_password:

                error = "Passwords do not match."

                cursor.close()

                return render_template(
                    "edit_profile.html",
                    user=user,
                    error=error
                )

            hashed_password = generate_password_hash(new_password)

            cursor.execute("""
                UPDATE users
                SET full_name=%s,
                    cnic=%s,
                    phone=%s,
                    photo=%s,
                    password=%s
                WHERE id=%s
            """, (
                full_name,
                cnic,
                phone,
                filename,
                hashed_password,
                session["id"]
            ))

        else:

            cursor.execute("""
                UPDATE users
                SET full_name=%s,
                    cnic=%s,
                    phone=%s,
                    photo=%s
                WHERE id=%s
            """, (
                full_name,
                cnic,
                phone,
                filename,
                session["id"]
            ))

        mysql.connection.commit()

        # Updated user fetch
        cursor.execute(
            "SELECT * FROM users WHERE id=%s",
            (session["id"],)
        )

        user = cursor.fetchone()

        success = "Profile updated successfully."

    cursor.close()

    return render_template(
        "edit_profile.html",
        user=user,
        success=success,
        error=error
    )

# VOTING PAGE

@app.route("/vote")
def vote():

    if "loggedin" not in session or session["role"] != "voter":
        return redirect("/")

    voter_id = session["id"]
    election_id = request.args.get("election_id")

    if not election_id:
        return redirect("/voter")

    cursor = mysql.connection.cursor(
        MySQLdb.cursors.DictCursor
    )

    # Election
    cursor.execute(
        """
        SELECT *
        FROM elections
        WHERE id=%s AND status=%s
        """,
        (election_id, "Active")
    )

    election = cursor.fetchone()

    if not election:
        cursor.close()
        return redirect("/voter")

    # Already voted?
    cursor.execute(
        """
        SELECT *
        FROM votes
        WHERE voter_id=%s
        AND election_id=%s
        """,
        (voter_id, election_id)
    )

    already_voted = cursor.fetchone() is not None

    # Candidates
    cursor.execute(
        """
        SELECT *
        FROM candidates
        WHERE election_id=%s
        """,
        (election_id,)
    )

    candidates = cursor.fetchall()

    cursor.close()

    return render_template(
        "vote.html",
        election=election,
        candidates=candidates,
        already_voted=already_voted
    )
    
# CAST VOTE

@app.route("/cast_vote", methods=["POST"])
def cast_vote():

    if "loggedin" not in session or session["role"] != "voter":
        return redirect("/")

    voter_id = session["id"]

    election_id = request.form.get("election_id")
    candidate_id = request.form.get("candidate_id")

    if not election_id or not candidate_id:
        return redirect("/voter")

    cursor = mysql.connection.cursor(
        MySQLdb.cursors.DictCursor
    )

    # Check election
    cursor.execute(
        """
        SELECT *
        FROM elections
        WHERE id=%s AND status=%s
        """,
        (election_id, "Active")
    )

    election = cursor.fetchone()

    if not election:
        cursor.close()
        return redirect("/voter")

    # Check duplicate vote
    cursor.execute(
        """
        SELECT *
        FROM votes
        WHERE voter_id=%s
        AND election_id=%s
        """,
        (voter_id, election_id)
    )

    already_voted = cursor.fetchone()

    if already_voted:
        cursor.close()

        return render_template(
            "vote_message.html",
            message="You have already voted in this election."
        )

    # Insert vote
    cursor.execute(
        """
        INSERT INTO votes
        (voter_id, candidate_id, election_id)
        VALUES (%s, %s, %s)
        """,
        (
            voter_id,
            candidate_id,
            election_id
        )
    )

    mysql.connection.commit()

    cursor.close()

    return render_template(
        "vote_message.html",
        message="Your vote has been submitted successfully!"
    )

# VOTE SUCCESS

@app.route("/vote_success")
def vote_success():

    message = session.pop(
        "message",
        "Vote Status"
    )

    return render_template(
        "vote_message.html",
        message=message
    )


# RESULTS

@app.route("/results")
def results():

    # ================= LOGIN CHECK =================

    if "loggedin" not in session:
        return redirect("/")

    cursor = mysql.connection.cursor(
        MySQLdb.cursors.DictCursor
    )

    # ================= ACTIVE / LATEST ELECTION =================

    cursor.execute("""
        SELECT *
        FROM elections
        WHERE status='Active'
        ORDER BY id DESC
        LIMIT 1
    """)

    election = cursor.fetchone()

    # Agar active election nahi hai to latest completed election lo
    if not election:

        cursor.execute("""
            SELECT *
            FROM elections
            WHERE status='Completed'
            ORDER BY id DESC
            LIMIT 1
        """)

        election = cursor.fetchone()

    # ================= NO ELECTION =================

    if not election:

        cursor.close()

        return render_template(
            "results.html",
            results=[],
            winner={
                "full_name": "No Winner",
                "total_votes": 0
            },
            total_votes=0,
            total_candidates=0,
            election=None
        )

    # ================= ELECTION RESULTS =================

    cursor.execute("""
        SELECT
            c.id,
            c.full_name,
            c.party_name,
            COUNT(v.id) AS total_votes

        FROM candidates c

        LEFT JOIN votes v
            ON c.id = v.candidate_id
            AND v.election_id = %s

        WHERE c.status='Active'

        GROUP BY
            c.id,
            c.full_name,
            c.party_name

        ORDER BY total_votes DESC
    """, (election["id"],))

    results = cursor.fetchall()

    # ================= TOTAL VOTES =================

    total_votes = sum(
        int(r["total_votes"])
        for r in results
    )

    # ================= TOTAL CANDIDATES =================

    total_candidates = len(results)

    # ================= PERCENTAGE =================

    for r in results:

        if total_votes > 0:

            r["percentage"] = round(
                (int(r["total_votes"]) / total_votes) * 100,
                2
            )

        else:

            r["percentage"] = 0

    # ================= WINNER =================

    if results and total_votes > 0:

        winner = results[0]

    else:

        winner = {
            "full_name": "No Winner",
            "party_name": "",
            "total_votes": 0
        }

    cursor.close()

    # ================= SEND TO TEMPLATE =================

    return render_template(
        "results.html",

        results=results,

        winner=winner,

        total_votes=total_votes,

        total_candidates=total_candidates,

        election=election
    )


# AI CHATBOT

@app.route("/chatbot")
def chatbot():

    if "loggedin" not in session:

        return redirect("/")

    return render_template(
        "chatbot.html"
    )


# ASK AI

@app.route(
    "/ask_ai",
    methods=["POST"]
)
def ask_ai():

    if "loggedin" not in session:

        return redirect("/")

    if model is None:

        return (
            "AI Assistant is not configured. "
            "Please set GEMINI_API_KEY."
        )

    message = request.form["message"]

    prompt = f"""
You are an AI Assistant for an Online Voting System.

Answer questions about:

- Voter Registration
- Elections
- Candidates
- Voting Process
- Election Results
- Basic Online Voting System information

Do not provide instructions for cheating,
manipulating votes, bypassing security,
or accessing unauthorized accounts.

User Question:

{message}
"""

    try:

        response = model.generate_content(
            prompt
        )

        return response.text

    except Exception as e:

        return (
            "AI Assistant error: "
            + str(e)
        )


# EXPORT VOTERS TO PDF

@app.route("/export_pdf")
def export_pdf():

    if (
        "loggedin" not in session
        or session["role"] != "admin"
    ):

        return redirect("/")

    cursor = mysql.connection.cursor(
        MySQLdb.cursors.DictCursor
    )

    cursor.execute(
        """
        SELECT
            id,
            full_name,
            email,
            role,
            status
        FROM users
        WHERE role='voter'
        """
    )

    voters_data = cursor.fetchall()

    cursor.close()

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer
    )

    data = [
        [
            "ID",
            "Name",
            "Email",
            "Role",
            "Status"
        ]
    ]

    for voter_data in voters_data:

        data.append(
            [
                voter_data["id"],
                voter_data["full_name"],
                voter_data["email"],
                voter_data["role"],
                voter_data["status"]
            ]
        )

    doc.build(
        [
            Table(data)
        ]
    )

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="voters.pdf",
        mimetype="application/pdf"
    )


# EXPORT VOTERS TO EXCEL

@app.route("/export_excel")
def export_excel():

    if (
        "loggedin" not in session
        or session["role"] != "admin"
    ):

        return redirect("/")

    cursor = mysql.connection.cursor(
        MySQLdb.cursors.DictCursor
    )

    cursor.execute(
        """
        SELECT
            id,
            full_name,
            email,
            role,
            status
        FROM users
        WHERE role='voter'
        """
    )

    voters_data = cursor.fetchall()

    cursor.close()

    wb = Workbook()

    ws = wb.active

    ws.title = "Voters"

    ws.append(
        [
            "ID",
            "Name",
            "Email",
            "Role",
            "Status"
        ]
    )

    for voter_data in voters_data:

        ws.append(
            [
                voter_data["id"],
                voter_data["full_name"],
                voter_data["email"],
                voter_data["role"],
                voter_data["status"]
            ]
        )

    buffer = io.BytesIO()

    wb.save(buffer)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="voters.xlsx",
        mimetype=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )
    )
    
@app.route("/settings")
def settings():

    if "loggedin" not in session or session["role"] != "admin":
        return redirect("/")

    return render_template("settings.html")

@app.route("/admin_profile", methods=["GET", "POST"])
def admin_profile():

    # ================= LOGIN CHECK =================

    if "loggedin" not in session or session["role"] != "admin":
        return redirect("/")

    admin_id = session["id"]

    cursor = mysql.connection.cursor(
        MySQLdb.cursors.DictCursor
    )

    message = ""
    message_type = ""

    # ================= UPDATE PROFILE =================

    if request.method == "POST":

        full_name = request.form["full_name"].strip()
        email = request.form["email"].strip()

        if not full_name or not email:

            message = "Name and Email are required."
            message_type = "danger"

        else:

            # Check duplicate email
            cursor.execute(
                """
                SELECT id
                FROM users
                WHERE email=%s AND id!=%s
                """,
                (email, admin_id)
            )

            existing_user = cursor.fetchone()

            if existing_user:

                message = "This email is already registered."
                message_type = "danger"

            else:

                cursor.execute(
                    """
                    UPDATE users
                    SET full_name=%s, email=%s
                    WHERE id=%s
                    """,
                    (full_name, email, admin_id)
                )

                mysql.connection.commit()

                # Update session name
                session["name"] = full_name

                message = "Profile updated successfully."
                message_type = "success"

    # ================= GET ADMIN =================

    cursor.execute(
        """
        SELECT *
        FROM users
        WHERE id=%s
        """,
        (admin_id,)
    )

    admin = cursor.fetchone()

    cursor.close()

    return render_template(
        "admin_profile.html",
        admin=admin,
        message=message,
        message_type=message_type
    )

@app.route("/change_password", methods=["GET", "POST"])
def change_password():

    if "loggedin" not in session or session["role"] != "admin":
        return redirect("/")

    message = ""

    if request.method == "POST":

        current_password = request.form["current_password"]
        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]

        if new_password != confirm_password:
            message = "New passwords do not match."

        else:

            cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

            cursor.execute(
                "SELECT password FROM users WHERE id=%s",
                (session["id"],)
            )

            admin = cursor.fetchone()

            if admin and admin["password"] == current_password:

                cursor.execute(
                    "UPDATE users SET password=%s WHERE id=%s",
                    (new_password, session["id"])
                )

                mysql.connection.commit()

                message = "Password changed successfully."

            else:
                message = "Current password is incorrect."

            cursor.close()

    return render_template(
        "change_password.html",
        message=message
    )

@app.route("/notifications")
def notifications():

    # ================= LOGIN CHECK =================

    if "loggedin" not in session:
        return redirect("/")

    role = session["role"]
    user_id = session["id"]

    cursor = mysql.connection.cursor(
        MySQLdb.cursors.DictCursor
    )

    # ==================================================
    # ADMIN NOTIFICATIONS
    # ==================================================

    if role == "admin":

        cursor.execute(
            """
            SELECT *
            FROM notifications
            WHERE user_id IS NULL
               OR user_id=%s
            ORDER BY created_at DESC
            """,
            (user_id,)
        )

        notifications = cursor.fetchall()

        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM notifications
            WHERE (user_id IS NULL OR user_id=%s)
              AND is_read=0
            """,
            (user_id,)
        )

        notification_count = cursor.fetchone()["total"]

    # ==================================================
    # VOTER NOTIFICATIONS
    # ==================================================

    elif role == "voter":

        cursor.execute(
            """
            SELECT *
            FROM notifications
            WHERE user_id IS NULL
               OR user_id=%s
            ORDER BY created_at DESC
            """,
            (user_id,)
        )

        notifications = cursor.fetchall()

        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM notifications
            WHERE (user_id IS NULL OR user_id=%s)
              AND is_read=0
            """,
            (user_id,)
        )

        notification_count = cursor.fetchone()["total"]

    else:

        cursor.close()
        return redirect("/")

    # ================= USER =================

    cursor.execute(
        """
        SELECT *
        FROM users
        WHERE id=%s
        """,
        (user_id,)
    )

    user = cursor.fetchone()

    # ================= CLOSE DATABASE =================

    cursor.close()

    # ================= SEND TO TEMPLATE =================

    return render_template(
        "notifications.html",
        notifications=notifications,
        notification_count=notification_count,
        unread_count=notification_count,
        user=user
    )
    
    
@app.route("/mark_notifications_read", methods=["POST"])
def mark_notifications_read():

    # ================= LOGIN CHECK =================

    if "loggedin" not in session or session["role"] != "voter":
        return redirect("/")

    # ================= DATABASE =================

    cursor = mysql.connection.cursor()

    # Mark all notifications available to this voter as read
    cursor.execute(
        """
        UPDATE notifications
        SET is_read=1
        WHERE user_id IS NULL
           OR user_id=%s
        """,
        (session["id"],)
    )

    mysql.connection.commit()

    # ================= CLOSE DATABASE =================

    cursor.close()

    # ================= BACK TO NOTIFICATIONS =================

    return redirect("/notifications")

@app.route("/admin/notifications")
def admin_notifications():

    if "loggedin" not in session or session["role"] != "admin":
        return redirect("/")

    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    # Voters
    cursor.execute("""
        SELECT id, full_name, email
        FROM users
        WHERE role='voter'
        ORDER BY full_name
    """)

    voters = cursor.fetchall()


    # Notification history
    cursor.execute("""
        SELECT *
        FROM notifications
        ORDER BY created_at DESC
    """)

    notifications = cursor.fetchall()


    # Total notifications
    cursor.execute("""
        SELECT COUNT(*) AS total
        FROM notifications
    """)

    notification_count = cursor.fetchone()["total"]


    cursor.close()

    return render_template(
        "admin_notifications.html",
        voters=voters,
        notifications=notifications,
        notification_count=notification_count
    )
    
@app.route("/admin/delete_notification/<int:id>")
def delete_notification(id):

    if "loggedin" not in session or session["role"] != "admin":
        return redirect("/")

    cursor = mysql.connection.cursor()

    cursor.execute(
        """
        DELETE FROM notifications
        WHERE id=%s
        """,
        (id,)
    )

    mysql.connection.commit()
    cursor.close()

    return redirect("/admin/notifications")

@app.route("/admin/send_notification", methods=["POST"])
def send_notification():

    if "loggedin" not in session or session["role"] != "admin":
        return redirect("/")

    title = request.form["title"]
    message = request.form["message"]
    user_id = request.form["user_id"]

    cursor = mysql.connection.cursor()

    if user_id == "all":

        cursor.execute("""
            INSERT INTO notifications
            (user_id, title, message, is_read)
            VALUES (NULL, %s, %s, 0)
        """, (title, message))

    else:

        cursor.execute("""
            INSERT INTO notifications
            (user_id, title, message, is_read)
            VALUES (%s, %s, %s, 0)
        """, (user_id, title, message))

    mysql.connection.commit()
    cursor.close()

    return redirect("/admin/notifications")

@app.route("/read_notification/<int:id>")
def read_notification(id):

    if "loggedin" not in session or session["role"] != "voter":
        return redirect("/")

    cursor = mysql.connection.cursor()

    cursor.execute(
        """
        UPDATE notifications
        SET is_read=1
        WHERE id=%s
        AND (user_id IS NULL OR user_id=%s)
        """,
        (
            id,
            session["id"]
        )
    )

    mysql.connection.commit()
    cursor.close()

    return redirect("/notifications")

@app.route("/user_settings")
def user_settings():

    if "loggedin" not in session or session["role"] != "voter":
        return redirect("/")

    return render_template("user_settings.html")

@app.route("/user_change_password", methods=["GET", "POST"])
def user_change_password():

    # ================= LOGIN CHECK =================

    if "loggedin" not in session or session["role"] != "voter":
        return redirect("/")

    message = ""
    message_type = ""

    # ================= CHANGE PASSWORD =================

    if request.method == "POST":

        current_password = request.form.get("current_password")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        if not current_password or not new_password or not confirm_password:

            message = "All fields are required."
            message_type = "danger"

        elif new_password != confirm_password:

            message = "New passwords do not match."
            message_type = "danger"

        elif len(new_password) < 6:

            message = "New password must be at least 6 characters."
            message_type = "danger"

        else:

            cursor = mysql.connection.cursor(
                MySQLdb.cursors.DictCursor
            )

            cursor.execute(
                """
                SELECT password
                FROM users
                WHERE id=%s
                """,
                (session["id"],)
            )

            user = cursor.fetchone()

            if user and user["password"] == current_password:

                cursor.execute(
                    """
                    UPDATE users
                    SET password=%s
                    WHERE id=%s
                    """,
                    (new_password, session["id"])
                )

                mysql.connection.commit()

                message = "Password changed successfully."
                message_type = "success"

            else:

                message = "Current password is incorrect."
                message_type = "danger"

            cursor.close()

    return render_template(
        "user_change_password.html",
        message=message,
        message_type=message_type
    )

# RUN APPLICATION
if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )