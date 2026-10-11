from typing import Dict, List, Any, Tuple
import time
from ortools.sat.python import cp_model

import database
import validation
import quality_score
import constraints

def generate_timetable(admin_id: int) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Main entry point for timetable generation using Google OR-Tools CP-SAT solver.
    Returns (success: bool, status_msg: str, result_payload: dict).
    """
    start_time = time.time()

    # Step 1: Input Validation
    is_valid_config, config_errors = validation.validate_input_configuration(admin_id)
    if not is_valid_config:
        return False, "Input Validation Failed", {
            'solver_status': 'VALIDATION_FAILED',
            'errors': config_errors,
            'quality_score': 0.0,
            'entries': []
        }

    # Step 2: Load Admin Data & Settings
    settings = database.get_admin_settings(admin_id)
    time_limit = settings.get('default_solver_time_limit', 60)

    classes = database.get_classes(admin_id)
    teachers = database.get_teachers(admin_id)
    subjects = database.get_subjects(admin_id)
    reqs = database.get_class_subject_requirements(admin_id)
    assignments = database.get_teacher_assignments(admin_id)
    availability = database.get_teacher_availability(admin_id)
    rooms = database.get_rooms(admin_id)
    labs = database.get_labs(admin_id)
    lab_reqs = database.get_lab_requirements(admin_id)
    days = [d['day_name'] for d in database.get_working_days(admin_id) if d['is_active']]
    periods = [p['period_number'] for p in database.get_periods(admin_id) if p['is_active']]
    breaks = database.get_breaks(admin_id)

    # Break period coverage: break after period N means slot N cannot be linked continuously to N+1
    break_after_periods = {b['after_period'] for b in breaks}

    # Mappings
    classes_dict = {c['id']: c for c in classes}
    teachers_dict = {t['id']: t for t in teachers}
    subjects_dict = {s['id']: s for s in subjects}
    rooms_dict = {r['id']: r for r in rooms}
    labs_dict = {l['id']: l for l in labs}

    # Faculty mapping: (class_id, subject_id) -> list of teacher_ids
    faculty_map = {}
    for a in assignments:
        key = (a['class_id'], a['subject_id'])
        if key not in faculty_map:
            faculty_map[key] = []
        faculty_map[key].append(a['teacher_id'])

    # Lab requirement mapping: subject_id -> list of lab_ids
    lab_subject_map = {}
    for lr in lab_reqs:
        sid = lr['subject_id']
        if sid not in lab_subject_map:
            lab_subject_map[sid] = []
        lab_subject_map[sid].append(lr['lab_id'])

    # Unavailable Teacher slots: (teacher_id, day_name, period_number)
    unavail_set = {(av['teacher_id'], av['day_name'], av['period_number']) for av in availability if not av['is_available']}

    # Constraint Toggles
    hard_toggles = constraints.get_enabled_hard_constraints(admin_id)
    soft_toggles = constraints.get_enabled_soft_constraints(admin_id)

    # Step 3: Decompose Requirements into Session Blocks
    # Each block is a tuple: (block_id, class_id, subject_id, consecutive_periods)
    blocks = []
    block_counter = 0
    for r in reqs:
        cid = r['class_id']
        sid = r['subject_id']
        req_p = r['periods_per_week']
        consec = r['consecutive_periods'] if r['consecutive_periods'] > 1 else 1

        n_blocks = req_p // consec if consec > 1 else req_p
        for b_idx in range(n_blocks):
            blocks.append({
                'block_id': block_counter,
                'class_id': cid,
                'subject_id': sid,
                'subject_type': r['subject_type'],
                'length': consec,
                'block_idx': b_idx
            })
            block_counter += 1

    # Step 4: Build CP-SAT Model
    model = cp_model.CpModel()
    X = {} # (block_id, day, start_period, resource_type, resource_id) -> BoolVar

    # Pre-determine valid resources for each block
    for b in blocks:
        cid = b['class_id']
        sid = b['subject_id']
        stype = b['subject_type']
        length = b['length']
        c_strength = classes_dict[cid]['student_strength']

        if stype == 'Lab':
            target_lab_ids = lab_subject_map.get(sid, [])
            valid_resources = [('LAB', lid) for lid in target_lab_ids if labs_dict[lid]['capacity'] >= c_strength]
        else:
            valid_resources = [('ROOM', rid) for rid in rooms_dict.keys() if rooms_dict[rid]['capacity'] >= c_strength]

        for d in days:
            for p in periods:
                # Check if block fits within day periods
                if p + length - 1 > max(periods):
                    continue

                # Check break collision for consecutive block (e.g. lab shouldn't span across lunch break)
                spans_break = False
                for step in range(length - 1):
                    if (p + step) in break_after_periods:
                        spans_break = True
                        break
                if spans_break:
                    continue

                for res_type, res_id in valid_resources:
                    var_name = f"X_b{b['block_id']}_d{d}_p{p}_{res_type}_{res_id}"
                    X[(b['block_id'], d, p, res_type, res_id)] = model.NewBoolVar(var_name)

    # Hard Constraint 1: Every block must be scheduled exactly once
    for b in blocks:
        b_id = b['block_id']
        possible_vars = [var for key, var in X.items() if key[0] == b_id]
        if not possible_vars:
            cname = classes_dict[b['class_id']]['name']
            sname = subjects_dict[b['subject_id']]['name']
            return False, "Infeasible Configuration", {
                'solver_status': 'INFEASIBLE',
                'errors': [f"No valid time slot or room/lab capacity found for Class '{cname}' - Subject '{sname}' (Length: {b['length']} periods)."],
                'quality_score': 0.0,
                'entries': []
            }
        model.Add(sum(possible_vars) == 1)

    # Hard Constraint 2: No Class Overlap
    # For each class c, day d, period t: at most 1 session active
    for cid in classes_dict.keys():
        for d in days:
            for t in periods:
                active_vars = []
                for b in blocks:
                    if b['class_id'] != cid:
                        continue
                    b_id, length = b['block_id'], b['length']
                    for p in periods:
                        if p <= t < p + length:
                            for key, var in X.items():
                                if key[0] == b_id and key[1] == d and key[2] == p:
                                    active_vars.append(var)
                if active_vars:
                    model.Add(sum(active_vars) <= 1)

    # Hard Constraint 3: No Teacher / Co-Teacher Overlap & Availability
    # For each teacher, day d, period t: at most 1 session active
    for tid in teachers_dict.keys():
        # Find all blocks where teacher tid is assigned
        t_blocks = [b for b in blocks if tid in faculty_map.get((b['class_id'], b['subject_id']), [])]
        if not t_blocks:
            continue

        for d in days:
            for t in periods:
                active_vars = []
                for b in t_blocks:
                    b_id, length = b['block_id'], b['length']
                    for p in periods:
                        if p <= t < p + length:
                            for key, var in X.items():
                                if key[0] == b_id and key[1] == d and key[2] == p:
                                    active_vars.append(var)

                # Teacher Availability check
                if (tid, d, t) in unavail_set:
                    for v in active_vars:
                        model.Add(v == 0)
                else:
                    if active_vars:
                        model.Add(sum(active_vars) <= 1)

    # Hard Constraint 4: No Room / Lab Overlap
    # For each classroom/lab, day d, period t: at most 1 session active
    for rid in rooms_dict.keys():
        for d in days:
            for t in periods:
                room_vars = []
                for b in blocks:
                    b_id, length = b['block_id'], b['length']
                    for p in periods:
                        if p <= t < p + length:
                            for key, var in X.items():
                                if key[0] == b_id and key[1] == d and key[2] == p and key[3] == 'ROOM' and key[4] == rid:
                                    room_vars.append(var)
                if room_vars:
                    model.Add(sum(room_vars) <= 1)

    for lid in labs_dict.keys():
        for d in days:
            for t in periods:
                lab_vars = []
                for b in blocks:
                    b_id, length = b['block_id'], b['length']
                    for p in periods:
                        if p <= t < p + length:
                            for key, var in X.items():
                                if key[0] == b_id and key[1] == d and key[2] == p and key[3] == 'LAB' and key[4] == lid:
                                    lab_vars.append(var)
                if lab_vars:
                    model.Add(sum(lab_vars) <= 1)

    # Hard Constraint 5: Max Teacher Daily Workload (HC10)
    if hard_toggles.get("HC10", True):
        for tid, t_info in teachers_dict.items():
            max_p = t_info.get('max_periods_per_day', 6)
            t_blocks = [b for b in blocks if tid in faculty_map.get((b['class_id'], b['subject_id']), [])]
            for d in days:
                d_terms = []
                for b in t_blocks:
                    b_id, length = b['block_id'], b['length']
                    for key, var in X.items():
                        if key[0] == b_id and key[1] == d:
                            d_terms.append(length * var)
                if d_terms:
                    model.Add(sum(d_terms) <= max_p)

    # Hard Constraint 6: At most 1 session of same Theory subject per class per day
    for cid in classes_dict.keys():
        for sid in subjects_dict.keys():
            if subjects_dict[sid]['type'] == 'Theory':
                cs_blocks = [b for b in blocks if b['class_id'] == cid and b['subject_id'] == sid]
                if len(cs_blocks) > 1:
                    for d in days:
                        d_vars = []
                        for b in cs_blocks:
                            b_id = b['block_id']
                            for key, var in X.items():
                                if key[0] == b_id and key[1] == d:
                                    d_vars.append(var)
                        if d_vars:
                            model.Add(sum(d_vars) <= 1)

    # Step 5: Soft Constraints & Objective Maximization
    objective_terms = []

    # Soft Constraint 1: Subject Day Distribution (SC1)
    if soft_toggles.get("SC1", {}).get("enabled", True):
        weight = soft_toggles.get("SC1", {}).get("weight", 8)
        for cid in classes_dict.keys():
            for sid in subjects_dict.keys():
                cs_blocks = [b for b in blocks if b['class_id'] == cid and b['subject_id'] == sid]
                if not cs_blocks:
                    continue
                for d in days:
                    day_active = model.NewBoolVar(f"DayActive_c{cid}_s{sid}_d{d}")
                    b_vars = [var for key, var in X.items() if key[0] in [b['block_id'] for b in cs_blocks] and key[1] == d]
                    if b_vars:
                        model.Add(sum(b_vars) >= day_active)
                        model.Add(sum(b_vars) <= len(b_vars) * day_active)
                        objective_terms.append(weight * day_active)

    # Soft Constraint 5: Optimal Room Capacity Match (SC5)
    if soft_toggles.get("SC5", {}).get("enabled", True):
        weight = soft_toggles.get("SC5", {}).get("weight", 4)
        for key, var in X.items():
            b_id, d, p, res_type, res_id = key
            b = next(b for b in blocks if b['block_id'] == b_id)
            c_strength = classes_dict[b['class_id']]['student_strength']
            cap = rooms_dict[res_id]['capacity'] if res_type == 'ROOM' else labs_dict[res_id]['capacity']
            wasted_cap = cap - c_strength
            # Penalize excess capacity
            penalty = min(wasted_cap, 50)
            objective_terms.append(-weight * penalty * var)

    if objective_terms:
        model.Maximize(sum(objective_terms))

    # Step 6: Invoke CP-SAT Solver
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_search_workers = 4

    solve_status_code = solver.Solve(model)
    status_str_map = {
        cp_model.OPTIMAL: 'OPTIMAL',
        cp_model.FEASIBLE: 'FEASIBLE',
        cp_model.INFEASIBLE: 'INFEASIBLE',
        cp_model.UNKNOWN: 'UNKNOWN',
        cp_model.MODEL_INVALID: 'INVALID'
    }
    solver_status = status_str_map.get(solve_status_code, 'UNKNOWN')

    if solver_status in ['OPTIMAL', 'FEASIBLE']:
        # Extract Solution Entries
        entries = []
        for key, var in X.items():
            if solver.Value(var) == 1:
                b_id, d, p, res_type, res_id = key
                b = next(b for b in blocks if b['block_id'] == b_id)
                cid = b['class_id']
                sid = b['subject_id']
                length = b['length']

                for step in range(length):
                    entries.append({
                        'class_id': cid,
                        'subject_id': sid,
                        'day_name': d,
                        'period_number': p + step,
                        'resource_type': res_type,
                        'resource_id': res_id
                    })

        # Calculate Quality Score
        q_result = quality_score.calculate_quality_score(admin_id, entries)
        q_score = q_result['overall_score']
        obj_val = float(solver.ObjectiveValue()) if objective_terms else 100.0

        # Save Run to Database
        run_id = database.save_timetable_run(
            admin_id=admin_id,
            solver_status=solver_status,
            objective_value=obj_val,
            quality_score=q_score,
            status='SUCCESS',
            message=f"Timetable generated successfully with status {solver_status}.",
            entries=entries
        )

        # Run Independent Validation
        is_valid_sol, sol_status, sol_errors = validation.validate_timetable_solution(admin_id, run_id)

        return True, f"Timetable generated successfully! ({solver_status})", {
            'run_id': run_id,
            'solver_status': solver_status,
            'objective_value': obj_val,
            'quality_score': q_score,
            'quality_breakdown': q_result['breakdown'],
            'is_valid_solution': is_valid_sol,
            'solution_validation_errors': sol_errors,
            'entries': entries
        }

    else:
        # Infeasible or Unknown
        conflict_reasons = []
        conflict_reasons.append("The constraint optimization solver could not satisfy all configured hard constraints.")
        conflict_reasons.append("Common causes include: insufficient room/lab capacity for student strength, excessive teacher unavailability, or over-constrained period limits.")

        run_id = database.save_timetable_run(
            admin_id=admin_id,
            solver_status=solver_status,
            objective_value=0.0,
            quality_score=0.0,
            status='FAILED',
            message=f"Timetable generation failed. Solver returned status: {solver_status}.",
            entries=[]
        )

        return False, "Timetable could not be generated.", {
            'run_id': run_id,
            'solver_status': solver_status,
            'errors': conflict_reasons,
            'quality_score': 0.0,
            'entries': []
        }
