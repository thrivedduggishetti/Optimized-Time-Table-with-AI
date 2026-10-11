import streamlit as st
import pandas as pd
from typing import List, Dict, Any
import database

def render_timetable_views(admin_id: int, run_id: int):
    """Renders interactive Class-wise, Teacher-wise, and Room-wise timetable views."""
    entries = database.get_timetable_entries_by_run(admin_id, run_id)
    if not entries:
        st.warning("No timetable entries available for the selected run.")
        return

    classes = database.get_classes(admin_id)
    teachers = database.get_teachers(admin_id)
    rooms = database.get_rooms(admin_id)
    labs = database.get_labs(admin_id)
    days = [d['day_name'] for d in database.get_working_days(admin_id) if d['is_active']]
    periods = database.get_periods(admin_id)
    breaks = database.get_breaks(admin_id)
    assignments = database.get_teacher_assignments(admin_id)

    # Lookup Maps
    classes_dict = {c['id']: c for c in classes}
    teachers_dict = {t['id']: t for t in teachers}
    rooms_dict = {r['id']: r for r in rooms}
    labs_dict = {l['id']: l for l in labs}

    # Faculty map: (class_id, subject_id) -> list of teacher names
    faculty_map = {}
    for a in assignments:
        key = (a['class_id'], a['subject_id'])
        if key not in faculty_map:
            faculty_map[key] = []
        tname = teachers_dict.get(a['teacher_id'], {}).get('name', f"Teacher #{a['teacher_id']}")
        if a['role'] == 'CO_TEACHER':
            faculty_map[key].append(f"{tname} (Co)")
        else:
            faculty_map[key].append(tname)

    tabs = st.tabs(["📚 Class-wise Timetable", "👨‍🏫 Teacher-wise Timetable", "🏛️ Room/Lab-wise Timetable"])

    # --- TAB 1: CLASS-WISE TIMETABLE ---
    with tabs[0]:
        st.subheader("Class-wise Timetable View")
        if not classes:
            st.info("No classes configured.")
        else:
            selected_class_id = st.selectbox(
                "Select Class:",
                options=[c['id'] for c in classes],
                format_func=lambda cid: classes_dict[cid]['name'],
                key="class_view_select"
            )

            sel_c = classes_dict[selected_class_id]
            st.markdown(f"**Class:** `{sel_c['name']}` | **Academic Year:** `{sel_c.get('academic_year', '')}` | **Strength:** `{sel_c['student_strength']} Students` | **Class Teacher:** `{sel_c.get('class_teacher', 'N/A')}`")

            # Filter entries for selected class
            c_entries = [e for e in entries if e['class_id'] == selected_class_id]
            entry_grid = {(e['day_name'], e['period_number']): e for e in c_entries}

            # Build Table Columns
            # Determine break positions
            break_after_set = {b['after_period'] for b in breaks}

            grid_data = []
            for d in days:
                row = {'Day': d}
                for p in periods:
                    pnum = p['period_number']
                    pname = p['period_name']
                    e = entry_grid.get((d, pnum))
                    if e:
                        scode = e['subject_code']
                        sname = e['subject_name']
                        fac_str = ", ".join(faculty_map.get((selected_class_id, e['subject_id']), ["Unassigned"]))
                        res_type = e['resource_type']
                        res_id = e['resource_id']
                        res_name = rooms_dict.get(res_id, {}).get('name') if res_type == 'ROOM' else labs_dict.get(res_id, {}).get('name')

                        cell_text = f"**{sname}** ({scode})\n\n👤 {fac_str}\n\n📍 {res_name}"
                    else:
                        cell_text = "— Free —"

                    row[f"{pname} ({p['start_time']}-{p['end_time']})"] = cell_text

                    if pnum in break_after_set:
                        b_info = next((b for b in breaks if b['after_period'] == pnum), None)
                        b_label = b_info['break_name'] if b_info else "Lunch Break"
                        row[f"☕ {b_label}"] = "☕ BREAK"

                grid_data.append(row)

            df_class = pd.DataFrame(grid_data)
            st.dataframe(df_class, use_container_width=True, hide_index=True)

            # Course Details Section Below Timetable
            st.markdown("---")
            st.subheader("📋 Course Details Summary")
            reqs = database.get_class_subject_requirements(admin_id, class_id=selected_class_id)
            if reqs:
                cdetails = []
                for r in reqs:
                    sid = r['subject_id']
                    fac_str = ", ".join(faculty_map.get((selected_class_id, sid), ["Unassigned"]))
                    # Find assigned resource from entries
                    res_names = set()
                    for e in c_entries:
                        if e['subject_id'] == sid:
                            rname = rooms_dict.get(e['resource_id'], {}).get('name') if e['resource_type'] == 'ROOM' else labs_dict.get(e['resource_id'], {}).get('name')
                            if rname:
                                res_names.add(rname)
                    res_str = ", ".join(res_names) if res_names else "N/A"

                    cdetails.append({
                        "Subject Code": r['subject_code'],
                        "Subject Name": r['subject_name'],
                        "Type": r['subject_type'],
                        "Faculty Member(s)": fac_str,
                        "Required Periods/Wk": r['periods_per_week'],
                        "Assigned Room/Lab": res_str
                    })
                st.table(pd.DataFrame(cdetails))

    # --- TAB 2: TEACHER-WISE TIMETABLE ---
    with tabs[1]:
        st.subheader("Teacher-wise Timetable View")
        if not teachers:
            st.info("No faculty members configured.")
        else:
            selected_teacher_id = st.selectbox(
                "Select Teacher:",
                options=[t['id'] for t in teachers],
                format_func=lambda tid: teachers_dict[tid]['name'],
                key="teacher_view_select"
            )

            sel_t = teachers_dict[selected_teacher_id]
            st.markdown(f"**Faculty:** `{sel_t['name']}` | **Email:** `{sel_t.get('email', 'N/A')}` | **Max Daily Periods:** `{sel_t['max_periods_per_day']}`")

            # Find all entries where this teacher is assigned (primary or co)
            t_entries = []
            for e in entries:
                f_list = faculty_map.get((e['class_id'], e['subject_id']), [])
                # match teacher name prefix
                t_name = sel_t['name']
                if any(t_name in f for f in f_list):
                    t_entries.append(e)

            entry_grid = {(e['day_name'], e['period_number']): e for e in t_entries}
            break_after_set = {b['after_period'] for b in breaks}

            grid_data = []
            for d in days:
                row = {'Day': d}
                for p in periods:
                    pnum = p['period_number']
                    pname = p['period_name']
                    e = entry_grid.get((d, pnum))
                    if e:
                        cname = classes_dict.get(e['class_id'], {}).get('name', '')
                        scode = e['subject_code']
                        sname = e['subject_name']
                        res_name = rooms_dict.get(e['resource_id'], {}).get('name') if e['resource_type'] == 'ROOM' else labs_dict.get(e['resource_id'], {}).get('name')

                        cell_text = f"**{cname}**\n\n📖 {sname} ({scode})\n\n📍 {res_name}"
                    else:
                        cell_text = "— Free —"

                    row[f"{pname} ({p['start_time']}-{p['end_time']})"] = cell_text

                    if pnum in break_after_set:
                        b_info = next((b for b in breaks if b['after_period'] == pnum), None)
                        b_label = b_info['break_name'] if b_info else "Lunch Break"
                        row[f"☕ {b_label}"] = "☕ BREAK"

                grid_data.append(row)

            st.dataframe(pd.DataFrame(grid_data), use_container_width=True, hide_index=True)

            # Teacher Workload Summary
            st.markdown("---")
            st.subheader("📊 Teaching Load Summary")
            total_periods = len(t_entries)
            st.metric("Total Teaching Periods / Week", f"{total_periods} Periods")

    # --- TAB 3: ROOM/LAB-WISE TIMETABLE ---
    with tabs[2]:
        st.subheader("Room & Laboratory Timetable View")
        all_resources = []
        for r in rooms:
            all_resources.append({'id': r['id'], 'type': 'ROOM', 'name': f"🏢 {r['name']} (Classroom, Cap: {r['capacity']})"})
        for l in labs:
            all_resources.append({'id': l['id'], 'type': 'LAB', 'name': f"🔬 {l['name']} (Laboratory, Cap: {l['capacity']})"})

        if not all_resources:
            st.info("No classrooms or labs configured.")
        else:
            selected_res_idx = st.selectbox(
                "Select Room / Lab:",
                options=list(range(len(all_resources))),
                format_func=lambda idx: all_resources[idx]['name'],
                key="room_view_select"
            )
            res_item = all_resources[selected_res_idx]

            # Filter entries for selected resource
            r_entries = [e for e in entries if e['resource_type'] == res_item['type'] and e['resource_id'] == res_item['id']]
            entry_grid = {(e['day_name'], e['period_number']): e for e in r_entries}
            break_after_set = {b['after_period'] for b in breaks}

            grid_data = []
            for d in days:
                row = {'Day': d}
                for p in periods:
                    pnum = p['period_number']
                    pname = p['period_name']
                    e = entry_grid.get((d, pnum))
                    if e:
                        cname = classes_dict.get(e['class_id'], {}).get('name', '')
                        sname = e['subject_name']
                        scode = e['subject_code']
                        fac_str = ", ".join(faculty_map.get((e['class_id'], e['subject_id']), ["Unassigned"]))

                        cell_text = f"**{cname}**\n\n📖 {sname} ({scode})\n\n👤 {fac_str}"
                    else:
                        cell_text = "— Vacant —"

                    row[f"{pname} ({p['start_time']}-{p['end_time']})"] = cell_text

                    if pnum in break_after_set:
                        b_info = next((b for b in breaks if b['after_period'] == pnum), None)
                        b_label = b_info['break_name'] if b_info else "Lunch Break"
                        row[f"☕ {b_label}"] = "☕ BREAK"

                grid_data.append(row)

            st.dataframe(pd.DataFrame(grid_data), use_container_width=True, hide_index=True)
