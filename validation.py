from typing import List, Dict, Any, Tuple
import database

def validate_input_configuration(admin_id: int) -> Tuple[bool, List[str]]:
    """
    Validates all data and configurations before invoking CP-SAT optimizer.
    Returns (is_valid: bool, errors: List[str]).
    """
    errors = []

    classes = database.get_classes(admin_id)
    if not classes:
        errors.append("No classes configured. Please add at least one class in Academic Setup.")

    teachers = database.get_teachers(admin_id)
    if not teachers:
        errors.append("No teachers configured. Please add faculty members in Academic Setup.")

    subjects = database.get_subjects(admin_id)
    if not subjects:
        errors.append("No subjects configured. Please add subjects in Academic Setup.")

    rooms = database.get_rooms(admin_id)
    labs = database.get_labs(admin_id)
    if not rooms and not labs:
        errors.append("No classrooms or laboratories configured. Please add resources in Resource Setup.")

    days = [d for d in database.get_working_days(admin_id) if d['is_active']]
    if not days:
        errors.append("No active working days configured. Please configure working days in Schedule Setup.")

    periods = [p for p in database.get_periods(admin_id) if p['is_active']]
    if not periods:
        errors.append("No active period timings configured. Please configure period timings in Schedule Setup.")

    if errors:
        return False, errors

    # Check Class-Subject Requirements
    reqs = database.get_class_subject_requirements(admin_id)
    if not reqs:
        errors.append("No Class-Subject requirements configured. Please assign subjects to classes with required periods/week.")

    # Check that each class has at least one requirement
    class_ids_with_req = {r['class_id'] for r in reqs}
    for c in classes:
        if c['id'] not in class_ids_with_req:
            errors.append(f"Class '{c['name']}' has no assigned subjects or period requirements.")

    # Check Faculty Assignments for each requirement
    assignments = database.get_teacher_assignments(admin_id)
    assigned_pairs = {(a['class_id'], a['subject_id']) for a in assignments}
    for r in reqs:
        if (r['class_id'], r['subject_id']) not in assigned_pairs:
            errors.append(f"Class '{r['class_name']}' - Subject '{r['subject_name']}' has no assigned faculty member.")

    # Check Lab Requirements for Lab subjects
    lab_reqs = database.get_lab_requirements(admin_id)
    lab_subject_ids = {lr['subject_id'] for lr in lab_reqs}

    for r in reqs:
        if r['subject_type'] == 'Lab':
            if r['subject_id'] not in lab_subject_ids:
                errors.append(f"Lab subject '{r['subject_name']}' is not mapped to any Laboratory in Lab Requirements.")

    # Check Capacity Feasibility
    for c in classes:
        c_strength = c['student_strength']
        # Check classrooms
        suitable_rooms = [rm for rm in rooms if rm['capacity'] >= c_strength]
        # Check labs
        suitable_labs = [l for l in labs if l['capacity'] >= c_strength]

        if not suitable_rooms and not suitable_labs:
            errors.append(f"Class '{c['name']}' (Strength: {c_strength}) has no classroom or lab with sufficient capacity.")

    # Check Total Available Period Capacity vs Total Required Periods
    total_slots = len(days) * len(periods)
    for c in classes:
        c_reqs = [r for r in reqs if r['class_id'] == c['id']]
        c_total_needed = sum(r['periods_per_week'] for r in c_reqs)
        if c_total_needed > total_slots:
            errors.append(
                f"Class '{c['name']}' requires {c_total_needed} periods/week, but only {total_slots} total slots are available "
                f"({len(days)} days × {len(periods)} periods)."
            )

    is_valid = len(errors) == 0
    return is_valid, errors

def validate_timetable_solution(admin_id: int, run_id: int) -> Tuple[bool, str, List[str]]:
    """
    Independently validates a generated timetable run against all hard constraints.
    Returns (is_valid: bool, status: 'VALID' | 'INVALID', errors: List[str]).
    """
    errors = []
    entries = database.get_timetable_entries_by_run(admin_id, run_id)
    if not entries:
        return False, "INVALID", ["Timetable contains no scheduled entries."]

    classes_dict = {c['id']: c for c in database.get_classes(admin_id)}
    teachers_dict = {t['id']: t for t in database.get_teachers(admin_id)}
    rooms_dict = {r['id']: r for r in database.get_rooms(admin_id)}
    labs_dict = {l['id']: l for l in database.get_labs(admin_id)}
    reqs = database.get_class_subject_requirements(admin_id)
    assignments = database.get_teacher_assignments(admin_id)
    availability = database.get_teacher_availability(admin_id)
    breaks = database.get_breaks(admin_id)
    break_periods = {b['after_period'] for b in breaks} # note: break after period N

    # Build Map of Class-Subject required periods & consec
    req_map = {(r['class_id'], r['subject_id']): r for r in reqs}

    # Build Map of (class_id, subject_id) -> list of teacher_ids (primary + co-teachers)
    faculty_map = {}
    for a in assignments:
        key = (a['class_id'], a['subject_id'])
        if key not in faculty_map:
            faculty_map[key] = []
        faculty_map[key].append(a['teacher_id'])

    # Build Unavailable Teacher Slots Set: (teacher_id, day_name, period_number)
    unavail_set = {(av['teacher_id'], av['day_name'], av['period_number']) for av in availability if not av['is_available']}

    # Track usage for conflict checks
    class_slots = {}  # (class_id, day_name, period_number) -> entry
    teacher_slots = {} # (teacher_id, day_name, period_number) -> entry
    room_slots = {}    # ('ROOM', room_id, day_name, period_number) -> entry
    lab_slots = {}     # ('LAB', lab_id, day_name, period_number) -> entry
    class_subject_counts = {} # (class_id, subject_id) -> count

    for entry in entries:
        cid = entry['class_id']
        sid = entry['subject_id']
        day = entry['day_name']
        pnum = entry['period_number']
        res_type = entry['resource_type']
        res_id = entry['resource_id']

        # 1. Class double booking
        c_key = (cid, day, pnum)
        if c_key in class_slots:
            cname = classes_dict.get(cid, {}).get('name', f'Class {cid}')
            errors.append(f"Class conflict: {cname} is double-booked on {day} Period {pnum}.")
        else:
            class_slots[c_key] = entry

        # 2. Teacher double booking & Availability
        t_ids = faculty_map.get((cid, sid), [])
        for tid in t_ids:
            t_key = (tid, day, pnum)
            if t_key in teacher_slots:
                tname = teachers_dict.get(tid, {}).get('name', f'Teacher {tid}')
                errors.append(f"Teacher conflict: {tname} is scheduled for multiple classes on {day} Period {pnum}.")
            else:
                teacher_slots[t_key] = entry

            if (tid, day, pnum) in unavail_set:
                tname = teachers_dict.get(tid, {}).get('name', f'Teacher {tid}')
                errors.append(f"Teacher availability constraint violated: {tname} is assigned on {day} Period {pnum} despite being unavailable.")

        # 3. Room/Lab conflict & Capacity
        c_strength = classes_dict.get(cid, {}).get('student_strength', 0)
        cname = classes_dict.get(cid, {}).get('name', f'Class {cid}')

        if res_type == 'ROOM':
            r_key = ('ROOM', res_id, day, pnum)
            if r_key in room_slots:
                rname = rooms_dict.get(res_id, {}).get('name', f'Room {res_id}')
                errors.append(f"Room conflict: Classroom '{rname}' is double-booked on {day} Period {pnum}.")
            else:
                room_slots[r_key] = entry

            rcap = rooms_dict.get(res_id, {}).get('capacity', 0)
            if rcap < c_strength:
                rname = rooms_dict.get(res_id, {}).get('name', f'Room {res_id}')
                errors.append(f"Room capacity error: Room '{rname}' (Capacity: {rcap}) is too small for class '{cname}' (Strength: {c_strength}).")

        elif res_type == 'LAB':
            l_key = ('LAB', res_id, day, pnum)
            if l_key in lab_slots:
                lname = labs_dict.get(res_id, {}).get('name', f'Lab {res_id}')
                errors.append(f"Lab conflict: Laboratory '{lname}' is double-booked on {day} Period {pnum}.")
            else:
                lab_slots[l_key] = entry

            lcap = labs_dict.get(res_id, {}).get('capacity', 0)
            if lcap < c_strength:
                lname = labs_dict.get(res_id, {}).get('name', f'Lab {res_id}')
                errors.append(f"Lab capacity error: Laboratory '{lname}' (Capacity: {lcap}) is too small for class '{cname}' (Strength: {c_strength}).")

        # Count periods
        cs_key = (cid, sid)
        class_subject_counts[cs_key] = class_subject_counts.get(cs_key, 0) + 1

    # 4. Check weekly period counts matching requirements
    for (cid, sid), r_info in req_map.items():
        req_p = r_info['periods_per_week']
        act_p = class_subject_counts.get((cid, sid), 0)
        if act_p != req_p:
            cname = classes_dict.get(cid, {}).get('name', f'Class {cid}')
            sname = r_info['subject_name']
            errors.append(f"Period requirement mismatch: Class '{cname}' - Subject '{sname}' requires {req_p} periods/week, but got {act_p}.")

    # 5. Check Lab Consecutive Blocks
    # Group entries by (class_id, subject_id, day_name)
    day_entries = {}
    for entry in entries:
        key = (entry['class_id'], entry['subject_id'], entry['day_name'])
        if key not in day_entries:
            day_entries[key] = []
        day_entries[key].append(entry['period_number'])

    for (cid, sid, day), pnums in day_entries.items():
        req_info = req_map.get((cid, sid))
        if req_info and req_info['subject_type'] == 'Lab' and req_info['consecutive_periods'] > 1:
            pnums_sorted = sorted(pnums)
            target_consec = req_info['consecutive_periods']
            # Check if periods form consecutive sequences of length target_consec
            i = 0
            while i < len(pnums_sorted):
                block = pnums_sorted[i : i + target_consec]
                if len(block) == target_consec:
                    expected = list(range(block[0], block[0] + target_consec))
                    if block != expected:
                        cname = classes_dict.get(cid, {}).get('name', f'Class {cid}')
                        sname = req_info['subject_name']
                        errors.append(f"Lab consecutiveness error: '{sname}' for '{cname}' on {day} periods {pnums_sorted} are not consecutive.")
                    i += target_consec
                else:
                    cname = classes_dict.get(cid, {}).get('name', f'Class {cid}')
                    sname = req_info['subject_name']
                    errors.append(f"Lab consecutiveness error: '{sname}' for '{cname}' on {day} has incomplete lab block {pnums_sorted}.")
                    break

    is_valid = len(errors) == 0
    status = "VALID" if is_valid else "INVALID"
    return is_valid, status, errors
