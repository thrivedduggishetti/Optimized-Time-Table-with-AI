import database

def load_demo_data_for_admin(admin_id: int) -> tuple[bool, str]:
    """
    Populates comprehensive realistic college demo data for the specified admin.
    """
    try:
        # 1. Update Admin Settings
        database.update_admin_settings(
            admin_id=admin_id,
            college_name="Geethanjali College of Engineering and Technology",
            academic_year="2026-27",
            department="Department of AIML",
            branch="AIML",
            time_limit=60
        )

        # Ensure working days exist
        existing_days = database.get_working_days(admin_id)
        if not existing_days:
            days = [("Monday", 1), ("Tuesday", 2), ("Wednesday", 3), ("Thursday", 4), ("Friday", 5), ("Saturday", 6)]
            for dname, dorder in days:
                database.add_working_day(admin_id, dname, dorder, 1)

        # Ensure periods exist
        existing_periods = database.get_periods(admin_id)
        if not existing_periods:
            plist = [
                (1, "P1", "09:00 AM", "09:55 AM"),
                (2, "P2", "09:55 AM", "10:50 AM"),
                (3, "P3", "10:50 AM", "11:45 AM"),
                (4, "P4", "11:45 AM", "12:40 PM"),
                (5, "P5", "01:30 PM", "02:25 PM"),
                (6, "P6", "02:25 PM", "03:20 PM")
            ]
            for pnum, pname, stime, etime in plist:
                database.add_period(admin_id, pnum, pname, stime, etime, 1)

        # Ensure breaks exist
        existing_breaks = database.get_breaks(admin_id)
        if not existing_breaks:
            database.add_break(admin_id, "Lunch Break", "12:40 PM", "01:30 PM", 4)

        # 2. Add Classes
        class_a_id = database.add_class(admin_id, "III B.Tech AIML-A", "2026-27", "3rd Year", "1st Semester", "AIML", "A", 40, "Dr. Rituparna Roy")
        class_b_id = database.add_class(admin_id, "III B.Tech AIML-B", "2026-27", "3rd Year", "1st Semester", "AIML", "B", 40, "Dr. G Bindu Madhavi")

        # 3. Add Teachers
        teachers_info = [
            ("Dr. Rituparna Roy", "rituparna@geethanjali.edu.in", 6),
            ("Dr. G Bindu Madhavi", "bindu@geethanjali.edu.in", 6),
            ("Shaik Akbar", "akbar@geethanjali.edu.in", 6),
            ("E Swapna", "swapna@geethanjali.edu.in", 6),
            ("Dr. S. K. Nuslin Bibi", "nuslin@geethanjali.edu.in", 6),
            ("Dr. K. Shobha Rani", "shobha@geethanjali.edu.in", 6),
            ("P. Swathi", "swathi@geethanjali.edu.in", 6),
            ("B. Nalini", "nalini@geethanjali.edu.in", 6),
            ("M. Supriya", "supriya@geethanjali.edu.in", 6)
        ]
        t_map = {}
        for name, email, max_p in teachers_info:
            tid = database.add_teacher(admin_id, name, email, max_p)
            t_map[name] = tid

        # 4. Add Subjects
        subjects_info = [
            ("SML", "Statistics for Machine Learning", "Theory", 3),
            ("CN", "Computer Networks", "Theory", 3),
            ("AI", "Artificial Intelligence", "Theory", 3),
            ("DWDM", "Data Warehousing and Data Mining", "Theory", 3),
            ("LR1", "Logical Reasoning-1", "Theory", 2),
            ("EPS", "English for Professional Success", "Theory", 2),
            ("SMLL", "Statistics for Machine Learning Lab", "Lab", 2),
            ("CNL", "Computer Networks Lab", "Lab", 2),
            ("AIL", "Artificial Intelligence Lab", "Lab", 2)
        ]
        s_map = {}
        for code, name, stype, dper in subjects_info:
            sid = database.add_subject(admin_id, code, name, stype, dper)
            s_map[code] = sid

        # 5. Class-Subject Requirements
        classes_list = [class_a_id, class_b_id]
        req_mapping = [
            ("SML", 3, 1),
            ("CN", 3, 1),
            ("AI", 3, 1),
            ("DWDM", 3, 1),
            ("LR1", 2, 1),
            ("EPS", 2, 1),
            ("SMLL", 2, 2), # 2 consecutive periods
            ("CNL", 2, 2),  # 2 consecutive periods
            ("AIL", 2, 2)   # 2 consecutive periods
        ]
        for cid in classes_list:
            for scode, per_wk, consec in req_mapping:
                sid = s_map[scode]
                database.add_class_subject_requirement(admin_id, cid, sid, per_wk, consec)

        # 6. Faculty Assignments
        for cid in classes_list:
            # SML
            database.add_teacher_assignment(admin_id, cid, s_map["SML"], t_map["Dr. Rituparna Roy"], "PRIMARY")
            # CN
            database.add_teacher_assignment(admin_id, cid, s_map["CN"], t_map["Dr. G Bindu Madhavi"], "PRIMARY")
            # AI
            database.add_teacher_assignment(admin_id, cid, s_map["AI"], t_map["Shaik Akbar"], "PRIMARY")
            # DWDM
            database.add_teacher_assignment(admin_id, cid, s_map["DWDM"], t_map["E Swapna"], "PRIMARY")
            # LR1
            database.add_teacher_assignment(admin_id, cid, s_map["LR1"], t_map["Dr. S. K. Nuslin Bibi"], "PRIMARY")
            # EPS
            database.add_teacher_assignment(admin_id, cid, s_map["EPS"], t_map["Dr. K. Shobha Rani"], "PRIMARY")

            # SMLL (Co-teachers)
            database.add_teacher_assignment(admin_id, cid, s_map["SMLL"], t_map["Dr. Rituparna Roy"], "PRIMARY")
            database.add_teacher_assignment(admin_id, cid, s_map["SMLL"], t_map["B. Nalini"], "CO_TEACHER")
            database.add_teacher_assignment(admin_id, cid, s_map["SMLL"], t_map["P. Swathi"], "CO_TEACHER")

            # CNL
            database.add_teacher_assignment(admin_id, cid, s_map["CNL"], t_map["Dr. G Bindu Madhavi"], "PRIMARY")
            database.add_teacher_assignment(admin_id, cid, s_map["CNL"], t_map["M. Supriya"], "CO_TEACHER")

            # AIL
            database.add_teacher_assignment(admin_id, cid, s_map["AIL"], t_map["Shaik Akbar"], "PRIMARY")
            database.add_teacher_assignment(admin_id, cid, s_map["AIL"], t_map["P. Swathi"], "CO_TEACHER")

        # 7. Rooms & Labs
        r1_id = database.add_room(admin_id, "E314", "Classroom", 60)
        r2_id = database.add_room(admin_id, "E315", "Classroom", 60)
        r3_id = database.add_room(admin_id, "E316", "Classroom", 60)

        lab_ai_id = database.add_lab(admin_id, "AI Lab", "AI Laboratory", 40)
        lab_cn_id = database.add_lab(admin_id, "CN Lab", "Computer Networking Laboratory", 40)
        lab_sml_id = database.add_lab(admin_id, "SML Lab", "Machine Learning Laboratory", 40)

        # 8. Lab Requirements Mapping
        database.add_lab_requirement(admin_id, s_map["SMLL"], lab_sml_id)
        database.add_lab_requirement(admin_id, s_map["CNL"], lab_cn_id)
        database.add_lab_requirement(admin_id, s_map["AIL"], lab_ai_id)

        # 9. Teacher Availability Example (Dr. Rituparna Roy unavailable Monday P2)
        database.set_teacher_availability(admin_id, t_map["Dr. Rituparna Roy"], "Monday", 2, 0)

        return True, "Demo data successfully loaded!"
    except Exception as e:
        return False, f"Error loading demo data: {str(e)}"
