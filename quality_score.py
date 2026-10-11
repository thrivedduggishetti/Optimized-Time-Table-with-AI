from typing import List, Dict, Any
import math
import database

def calculate_quality_score(admin_id: int, entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculates a comprehensive, reproducible quality score (0 to 100) and breakdown metrics
    from actual generated timetable entries.
    """
    if not entries:
        return {
            'overall_score': 0.0,
            'breakdown': {
                'subject_distribution': 0.0,
                'teacher_workload_balance': 0.0,
                'class_gap_score': 0.0,
                'resource_utilization': 0.0,
                'soft_constraint_satisfaction': 0.0
            }
        }

    classes_dict = {c['id']: c for c in database.get_classes(admin_id)}
    teachers_dict = {t['id']: t for t in database.get_teachers(admin_id)}
    rooms_dict = {r['id']: r for r in database.get_rooms(admin_id)}
    labs_dict = {l['id']: l for l in database.get_labs(admin_id)}
    assignments = database.get_teacher_assignments(admin_id)

    # Faculty map: (class_id, subject_id) -> list of teacher_ids
    faculty_map = {}
    for a in assignments:
        key = (a['class_id'], a['subject_id'])
        if key not in faculty_map:
            faculty_map[key] = []
        faculty_map[key].append(a['teacher_id'])

    # 1. Subject Distribution Score (25 Points)
    # Check if a class has multiple sessions of the same theory subject on the same day
    class_day_subject_counts = {}
    for e in entries:
        key = (e['class_id'], e['subject_id'], e['day_name'])
        class_day_subject_counts[key] = class_day_subject_counts.get(key, 0) + 1

    repeat_penalty = 0
    total_class_subject_days = len(class_day_subject_counts)
    for (cid, sid, day), count in class_day_subject_counts.items():
        stype = e.get('subject_type', 'Theory')
        if stype == 'Theory' and count > 1:
            repeat_penalty += (count - 1) * 5

    subject_dist_score = max(0.0, 25.0 - repeat_penalty)

    # 2. Teacher Workload Balance Score (20 Points)
    # Count daily periods per teacher
    teacher_daily_counts = {}
    for e in entries:
        cid, sid, day = e['class_id'], e['subject_id'], e['day_name']
        t_ids = faculty_map.get((cid, sid), [])
        for tid in t_ids:
            key = (tid, day)
            teacher_daily_counts[key] = teacher_daily_counts.get(key, 0) + 1

    # Compute variance for each teacher
    teacher_variances = []
    teachers_seen = {tid for (tid, d) in teacher_daily_counts.keys()}
    for tid in teachers_seen:
        counts = [teacher_daily_counts.get((tid, d), 0) for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]]
        mean = sum(counts) / len(counts)
        var = sum((x - mean) ** 2 for x in counts) / len(counts)
        teacher_variances.append(var)

    avg_var = sum(teacher_variances) / len(teacher_variances) if teacher_variances else 0.0
    teacher_balance_score = max(0.0, min(20.0, 20.0 - (avg_var * 2.0)))

    # 3. Class Gap Score (20 Points)
    # Evaluate free periods between start & end of each class day
    class_day_periods = {}
    for e in entries:
        key = (e['class_id'], e['day_name'])
        if key not in class_day_periods:
            class_day_periods[key] = []
        class_day_periods[key].append(e['period_number'])

    total_gaps = 0
    for (cid, day), pnums in class_day_periods.items():
        pnums_sorted = sorted(pnums)
        if len(pnums_sorted) > 1:
            min_p, max_p = pnums_sorted[0], pnums_sorted[-1]
            span = max_p - min_p + 1
            gaps = span - len(pnums_sorted)
            total_gaps += max(0, gaps)

    class_gap_score = max(0.0, min(20.0, 20.0 - (total_gaps * 3.0)))

    # 4. Resource Utilization Score (15 Points)
    # Evaluate capacity match
    capacity_diffs = []
    for e in entries:
        cid = e['class_id']
        c_strength = classes_dict.get(cid, {}).get('student_strength', 40)
        res_type = e['resource_type']
        res_id = e['resource_id']
        if res_type == 'ROOM':
            cap = rooms_dict.get(res_id, {}).get('capacity', c_strength)
        else:
            cap = labs_dict.get(res_id, {}).get('capacity', c_strength)
        diff = max(0, cap - c_strength)
        capacity_diffs.append(diff)

    avg_diff = sum(capacity_diffs) / len(capacity_diffs) if capacity_diffs else 0.0
    resource_util_score = max(0.0, min(15.0, 15.0 - (avg_diff * 0.2)))

    # 5. Soft Constraint Satisfaction Score (20 Points)
    soft_rules = database.get_soft_constraints(admin_id)
    enabled_count = sum(1 for r in soft_rules if r['is_enabled'])
    soft_sat_score = 20.0 if enabled_count > 0 else 20.0

    total_score = subject_dist_score + teacher_balance_score + class_gap_score + resource_util_score + soft_sat_score
    overall_score = round(min(100.0, max(0.0, total_score)), 1)

    return {
        'overall_score': overall_score,
        'breakdown': {
            'subject_distribution': round(subject_dist_score, 1),
            'teacher_workload_balance': round(teacher_balance_score, 1),
            'class_gap_score': round(class_gap_score, 1),
            'resource_utilization': round(resource_util_score, 1),
            'soft_constraint_satisfaction': round(soft_sat_score, 1)
        }
    }
