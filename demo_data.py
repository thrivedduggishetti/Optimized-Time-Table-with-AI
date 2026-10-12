import database


def load_demo_data_for_admin(admin_id: int) -> tuple[bool, str]:
    """
    Populate realistic demo data for one administrator.
    Safe to retry: existing records are reused instead of duplicated.
    """
    try:
        database.update_admin_settings(
            admin_id=admin_id,
            college_name="Geethanjali College of Engineering and Technology",
            academic_year="2026-27",
            department="Department of AIML",
            branch="AIML",
            time_limit=60,
        )

        # Working days, periods, and breaks: create only when missing.
        existing_days = database.get_working_days(admin_id)
        if not existing_days:
            for dname, dorder in [
                ("Monday", 1), ("Tuesday", 2), ("Wednesday", 3),
                ("Thursday", 4), ("Friday", 5), ("Saturday", 6),
            ]:
                database.add_working_day(admin_id, dname, dorder, 1)

        existing_periods = database.get_periods(admin_id)
        if not existing_periods:
            for pnum, pname, stime, etime in [
                (1, "P1", "09:00 AM", "09:55 AM"),
                (2, "P2", "09:55 AM", "10:50 AM"),
                (3, "P3", "10:50 AM", "11:45 AM"),
                (4, "P4", "11:45 AM", "12:40 PM"),
                (5, "P5", "01:30 PM", "02:25 PM"),
                (6, "P6", "02:25 PM", "03:20 PM"),
            ]:
                database.add_period(admin_id, pnum, pname, stime, etime, 1)

        if not database.get_breaks(admin_id):
            database.add_break(admin_id, "Lunch Break", "12:40 PM", "01:30 PM", 4)

        # Classes: reuse by name.
        classes_by_name = {c["name"]: c for c in database.get_classes(admin_id)}
        class_specs = [
            ("III B.Tech AIML-A", "A", "Dr. Rituparna Roy"),
            ("III B.Tech AIML-B", "B", "Dr. G Bindu Madhavi"),
        ]
        class_ids = []
        for name, section, class_teacher in class_specs:
            if name in classes_by_name:
                cid = classes_by_name[name]["id"]
            else:
                cid = database.add_class(
                    admin_id, name, "2026-27", "3rd Year", "1st Semester",
                    "AIML", section, 40, class_teacher
                )
            class_ids.append(cid)

        # Teachers: reuse by name.
        teacher_by_name = {t["name"]: t for t in database.get_teachers(admin_id)}
        teachers_info = [
            ("Dr. Rituparna Roy", "rituparna@geethanjali.edu.in", 6),
            ("Dr. G Bindu Madhavi", "bindu@geethanjali.edu.in", 6),
            ("Shaik Akbar", "akbar@geethanjali.edu.in", 6),
            ("E Swapna", "swapna@geethanjali.edu.in", 6),
            ("Dr. S. K. Nuslin Bibi", "nuslin@geethanjali.edu.in", 6),
            ("Dr. K. Shobha Rani", "shobha@geethanjali.edu.in", 6),
            ("P. Swathi", "swathi@geethanjali.edu.in", 6),
            ("B. Nalini", "nalini@geethanjali.edu.in", 6),
            ("M. Supriya", "supriya@geethanjali.edu.in", 6),
        ]
        t_map = {}
        for name, email, max_p in teachers_info:
            if name in teacher_by_name:
                tid = teacher_by_name[name]["id"]
            else:
                tid = database.add_teacher(admin_id, name, email, max_p)
            t_map[name] = tid

        # Subjects: reuse by subject code.
        subject_by_code = {s["code"]: s for s in database.get_subjects(admin_id)}
        subjects_info = [
            ("SML", "Statistics for Machine Learning", "Theory", 3),
            ("CN", "Computer Networks", "Theory", 3),
            ("AI", "Artificial Intelligence", "Theory", 3),
            ("DWDM", "Data Warehousing and Data Mining", "Theory", 3),
            ("LR1", "Logical Reasoning-1", "Theory", 2),
            ("EPS", "English for Professional Success", "Theory", 2),
            ("SMLL", "Statistics for Machine Learning Lab", "Lab", 2),
            ("CNL", "Computer Networks Lab", "Lab", 2),
            ("AIL", "Artificial Intelligence Lab", "Lab", 2),
        ]
        s_map = {}
        for code, name, stype, dper in subjects_info:
            if code in subject_by_code:
                sid = subject_by_code[code]["id"]
            else:
                sid = database.add_subject(admin_id, code, name, stype, dper)
            s_map[code] = sid

        # Class-subject requirements: reuse existing combinations.
        existing_reqs = database.get_class_subject_requirements(admin_id)
        req_keys = {(r["class_id"], r["subject_id"]) for r in existing_reqs}
        req_mapping = [
            ("SML", 3, 1), ("CN", 3, 1), ("AI", 3, 1),
            ("DWDM", 3, 1), ("LR1", 2, 1), ("EPS", 2, 1),
            ("SMLL", 2, 2), ("CNL", 2, 2), ("AIL", 2, 2),
        ]
        for cid in class_ids:
            for code, periods_per_week, consecutive in req_mapping:
                sid = s_map[code]
                if (cid, sid) not in req_keys:
                    database.add_class_subject_requirement(
                        admin_id, cid, sid, periods_per_week, consecutive
                    )

        # Faculty assignments: avoid adding duplicate assignment tuples.
        existing_assignments = database.get_teacher_assignments(admin_id)
        assignment_keys = {
            (a["class_id"], a["subject_id"], a["teacher_id"], a.get("role", "PRIMARY"))
            for a in existing_assignments
        }
        assignment_specs = [
            ("SML", "Dr. Rituparna Roy", "PRIMARY"),
            ("CN", "Dr. G Bindu Madhavi", "PRIMARY"),
            ("AI", "Shaik Akbar", "PRIMARY"),
            ("DWDM", "E Swapna", "PRIMARY"),
            ("LR1", "Dr. S. K. Nuslin Bibi", "PRIMARY"),
            ("EPS", "Dr. K. Shobha Rani", "PRIMARY"),
            ("SMLL", "Dr. Rituparna Roy", "PRIMARY"),
            ("SMLL", "B. Nalini", "CO_TEACHER"),
            ("SMLL", "P. Swathi", "CO_TEACHER"),
            ("CNL", "Dr. G Bindu Madhavi", "PRIMARY"),
            ("CNL", "M. Supriya", "CO_TEACHER"),
            ("AIL", "Shaik Akbar", "PRIMARY"),
            ("AIL", "P. Swathi", "CO_TEACHER"),
        ]
        for cid in class_ids:
            for code, teacher_name, role in assignment_specs:
                key = (cid, s_map[code], t_map[teacher_name], role)
                if key not in assignment_keys:
                    database.add_teacher_assignment(admin_id, *key[:3], role)
                    assignment_keys.add(key)

        # Rooms and labs: reuse by name.
        rooms_by_name = {r["name"]: r for r in database.get_rooms(admin_id)}
        for name, room_type, capacity in [
            ("E314", "Classroom", 60),
            ("E315", "Classroom", 60),
            ("E316", "Classroom", 60),
        ]:
            if name not in rooms_by_name:
                database.add_room(admin_id, name, room_type, capacity)

        labs_by_name = {l["name"]: l for l in database.get_labs(admin_id)}
        for name, lab_type, capacity in [
            ("AI Lab", "AI Laboratory", 40),
            ("CN Lab", "Computer Networking Laboratory", 40),
            ("SML Lab", "Machine Learning Laboratory", 40),
        ]:
            if name not in labs_by_name:
                database.add_lab(admin_id, name, lab_type, capacity)

        # Lab mappings: reuse existing mappings.
        labs_by_name = {l["name"]: l for l in database.get_labs(admin_id)}
        existing_lab_reqs = database.get_lab_requirements(admin_id)
        lab_req_keys = {(r["subject_id"], r["lab_id"]) for r in existing_lab_reqs}
        for code, lab_name in [
            ("SMLL", "SML Lab"), ("CNL", "CN Lab"), ("AIL", "AI Lab")
        ]:
            key = (s_map[code], labs_by_name[lab_name]["id"])
            if key not in lab_req_keys:
                database.add_lab_requirement(admin_id, *key)

        # Example availability setting: mark unavailable only if not already recorded.
        availability = database.get_teacher_availability(admin_id, t_map["Dr. Rituparna Roy"])
        if not any(a["day_name"] == "Monday" and a["period_number"] == 2 for a in availability):
            database.set_teacher_availability(
                admin_id, t_map["Dr. Rituparna Roy"], "Monday", 2, 0
            )

        return True, "Demo data loaded or verified successfully. You can now validate and generate a timetable."
    except Exception as e:
        # Return the failure to the UI so the specific cause is visible there.
        return False, f"Error loading demo data: {type(e).__name__}: {e}"
