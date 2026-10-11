import io
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import database

def generate_excel_export(admin_id: int, run_id: int) -> bytes:
    """
    Generates a professional multi-sheet Excel workbook using openpyxl.
    Sheets:
      1. Class Timetables
      2. Teacher Timetables
      3. Room Timetables
      4. Course Details
      5. Generation Summary
      6. Quality Analysis
    Returns raw bytes of the workbook file.
    """
    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    entries = database.get_timetable_entries_by_run(admin_id, run_id)
    runs = database.get_timetable_runs(admin_id)
    current_run = next((r for r in runs if r['id'] == run_id), None)
    settings = database.get_admin_settings(admin_id)

    classes = database.get_classes(admin_id)
    teachers = database.get_teachers(admin_id)
    rooms = database.get_rooms(admin_id)
    labs = database.get_labs(admin_id)
    days = [d['day_name'] for d in database.get_working_days(admin_id) if d['is_active']]
    periods = database.get_periods(admin_id)
    breaks = database.get_breaks(admin_id)
    assignments = database.get_teacher_assignments(admin_id)

    classes_dict = {c['id']: c for c in classes}
    teachers_dict = {t['id']: t for t in teachers}
    rooms_dict = {r['id']: r for r in rooms}
    labs_dict = {l['id']: l for l in labs}

    faculty_map = {}
    for a in assignments:
        key = (a['class_id'], a['subject_id'])
        if key not in faculty_map:
            faculty_map[key] = []
        tname = teachers_dict.get(a['teacher_id'], {}).get('name', f"Teacher #{a['teacher_id']}")
        faculty_map[key].append(tname)

    # Styles
    title_font = Font(name="Arial", size=14, bold=True, color="FFFFFF")
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    sub_header_font = Font(name="Arial", size=11, bold=True, color="1E293B")
    cell_font = Font(name="Arial", size=10, color="0F172A")
    bold_font = Font(name="Arial", size=10, bold=True, color="0F172A")

    title_fill = PatternFill(start_color="312E81", end_color="312E81", fill_type="solid") # Dark Indigo
    header_fill = PatternFill(start_color="4338CA", end_color="4338CA", fill_type="solid") # Indigo
    break_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")  # Amber Light
    accent_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid") # Slate Light

    thin_border_side = Side(style='thin', color='CBD5E1')
    thick_border_side = Side(style='medium', color='64748B')
    border_all = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)

    align_center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    align_left = Alignment(horizontal='left', vertical='center', wrap_text=True)

    break_after_set = {b['after_period'] for b in breaks}

    # --- SHEET 1: CLASS TIMETABLES ---
    ws1 = wb.create_sheet(title="Class Timetables")
    ws1.views.sheetView[0].showGridLines = True

    row_num = 1
    # Title Banner
    ws1.merge_cells(start_row=row_num, start_column=1, end_row=row_num+1, end_column=len(periods) + len(breaks) + 1)
    cell = ws1.cell(row=row_num, column=1, value=f"{settings['college_name'].upper()}\nOPTIMIZED TIME TABLE WITH AI - CLASS TIMETABLES")
    cell.font = title_font
    cell.fill = title_fill
    cell.alignment = align_center
    row_num += 3

    for c in classes:
        cid = c['id']
        ws1.cell(row=row_num, column=1, value=f"CLASS: {c['name']} (Academic Year: {c.get('academic_year', 'N/A')}, Strength: {c['student_strength']})").font = sub_header_font
        row_num += 1

        headers = ["Day"]
        for p in periods:
            headers.append(f"{p['period_name']}\n({p['start_time']}-{p['end_time']})")
            if p['period_number'] in break_after_set:
                b_info = next((b for b in breaks if b['after_period'] == p['period_number']), None)
                headers.append(f"BREAK\n({b_info['break_name']})" if b_info else "LUNCH\nBREAK")

        # Write Header Row
        for col_idx, h in enumerate(headers, start=1):
            c_cell = ws1.cell(row=row_num, column=col_idx, value=h)
            c_cell.font = header_font
            c_cell.fill = header_fill
            c_cell.alignment = align_center
            c_cell.border = border_all
        row_num += 1

        # Write Days Data
        c_entries = [e for e in entries if e['class_id'] == cid]
        entry_grid = {(e['day_name'], e['period_number']): e for e in c_entries}

        for d in days:
            ws1.cell(row=row_num, column=1, value=d).font = bold_font
            ws1.cell(row=row_num, column=1).alignment = align_center
            ws1.cell(row=row_num, column=1).border = border_all

            col_idx = 2
            for p in periods:
                pnum = p['period_number']
                e = entry_grid.get((d, pnum))
                if e:
                    sname = e['subject_name']
                    scode = e['subject_code']
                    fac_str = ", ".join(faculty_map.get((cid, e['subject_id']), ["Unassigned"]))
                    res_name = rooms_dict.get(e['resource_id'], {}).get('name') if e['resource_type'] == 'ROOM' else labs_dict.get(e['resource_id'], {}).get('name')
                    val_text = f"{sname} ({scode})\nFaculty: {fac_str}\nRoom: {res_name}"
                else:
                    val_text = "— Free —"

                c_cell = ws1.cell(row=row_num, column=col_idx, value=val_text)
                c_cell.font = cell_font
                c_cell.alignment = align_center
                c_cell.border = border_all
                col_idx += 1

                if pnum in break_after_set:
                    b_cell = ws1.cell(row=row_num, column=col_idx, value="LUNCH / BREAK")
                    b_cell.font = bold_font
                    b_cell.fill = break_fill
                    b_cell.alignment = align_center
                    b_cell.border = border_all
                    col_idx += 1

            row_num += 1
        row_num += 2 # gap between classes

    # --- SHEET 2: TEACHER TIMETABLES ---
    ws2 = wb.create_sheet(title="Teacher Timetables")
    ws2.views.sheetView[0].showGridLines = True
    row_num = 1

    ws2.merge_cells(start_row=row_num, start_column=1, end_row=row_num+1, end_column=len(periods) + len(breaks) + 1)
    cell = ws2.cell(row=row_num, column=1, value=f"{settings['college_name'].upper()}\nOPTIMIZED TIME TABLE WITH AI - FACULTY TIMETABLES")
    cell.font = title_font
    cell.fill = title_fill
    cell.alignment = align_center
    row_num += 3

    for t in teachers:
        tid = t['id']
        t_name = t['name']
        ws2.cell(row=row_num, column=1, value=f"FACULTY: {t_name} (Email: {t.get('email', 'N/A')})").font = sub_header_font
        row_num += 1

        headers = ["Day"]
        for p in periods:
            headers.append(f"{p['period_name']}\n({p['start_time']}-{p['end_time']})")
            if p['period_number'] in break_after_set:
                headers.append("LUNCH / BREAK")

        for col_idx, h in enumerate(headers, start=1):
            c_cell = ws2.cell(row=row_num, column=col_idx, value=h)
            c_cell.font = header_font
            c_cell.fill = header_fill
            c_cell.alignment = align_center
            c_cell.border = border_all
        row_num += 1

        # Teacher entries
        t_entries = []
        for e in entries:
            f_list = faculty_map.get((e['class_id'], e['subject_id']), [])
            if any(t_name in f for f in f_list):
                t_entries.append(e)

        entry_grid = {(e['day_name'], e['period_number']): e for e in t_entries}

        for d in days:
            ws2.cell(row=row_num, column=1, value=d).font = bold_font
            ws2.cell(row=row_num, column=1).alignment = align_center
            ws2.cell(row=row_num, column=1).border = border_all

            col_idx = 2
            for p in periods:
                pnum = p['period_number']
                e = entry_grid.get((d, pnum))
                if e:
                    cname = classes_dict.get(e['class_id'], {}).get('name', '')
                    sname = e['subject_name']
                    scode = e['subject_code']
                    res_name = rooms_dict.get(e['resource_id'], {}).get('name') if e['resource_type'] == 'ROOM' else labs_dict.get(e['resource_id'], {}).get('name')
                    val_text = f"Class: {cname}\n{sname} ({scode})\nRoom: {res_name}"
                else:
                    val_text = "— Free —"

                c_cell = ws2.cell(row=row_num, column=col_idx, value=val_text)
                c_cell.font = cell_font
                c_cell.alignment = align_center
                c_cell.border = border_all
                col_idx += 1

                if pnum in break_after_set:
                    b_cell = ws2.cell(row=row_num, column=col_idx, value="LUNCH / BREAK")
                    b_cell.font = bold_font
                    b_cell.fill = break_fill
                    b_cell.alignment = align_center
                    b_cell.border = border_all
                    col_idx += 1

            row_num += 1
        row_num += 2

    # --- SHEET 3: ROOM & LAB TIMETABLES ---
    ws3 = wb.create_sheet(title="Room & Lab Timetables")
    ws3.views.sheetView[0].showGridLines = True
    row_num = 1

    ws3.merge_cells(start_row=row_num, start_column=1, end_row=row_num+1, end_column=len(periods) + len(breaks) + 1)
    cell = ws3.cell(row=row_num, column=1, value=f"{settings['college_name'].upper()}\nOPTIMIZED TIME TABLE WITH AI - RESOURCE TIMETABLES")
    cell.font = title_font
    cell.fill = title_fill
    cell.alignment = align_center
    row_num += 3

    all_res = [('ROOM', r['id'], f"CLASSROOM: {r['name']} (Cap: {r['capacity']})") for r in rooms] + \
              [('LAB', l['id'], f"LABORATORY: {l['name']} (Cap: {l['capacity']})") for l in labs]

    for r_type, r_id, r_label in all_res:
        ws3.cell(row=row_num, column=1, value=r_label).font = sub_header_font
        row_num += 1

        headers = ["Day"]
        for p in periods:
            headers.append(f"{p['period_name']}\n({p['start_time']}-{p['end_time']})")
            if p['period_number'] in break_after_set:
                headers.append("LUNCH / BREAK")

        for col_idx, h in enumerate(headers, start=1):
            c_cell = ws3.cell(row=row_num, column=col_idx, value=h)
            c_cell.font = header_font
            c_cell.fill = header_fill
            c_cell.alignment = align_center
            c_cell.border = border_all
        row_num += 1

        r_entries = [e for e in entries if e['resource_type'] == r_type and e['resource_id'] == r_id]
        entry_grid = {(e['day_name'], e['period_number']): e for e in r_entries}

        for d in days:
            ws3.cell(row=row_num, column=1, value=d).font = bold_font
            ws3.cell(row=row_num, column=1).alignment = align_center
            ws3.cell(row=row_num, column=1).border = border_all

            col_idx = 2
            for p in periods:
                pnum = p['period_number']
                e = entry_grid.get((d, pnum))
                if e:
                    cname = classes_dict.get(e['class_id'], {}).get('name', '')
                    sname = e['subject_name']
                    fac_str = ", ".join(faculty_map.get((e['class_id'], e['subject_id']), ["Unassigned"]))
                    val_text = f"Class: {cname}\n{sname}\nFaculty: {fac_str}"
                else:
                    val_text = "— Vacant —"

                c_cell = ws3.cell(row=row_num, column=col_idx, value=val_text)
                c_cell.font = cell_font
                c_cell.alignment = align_center
                c_cell.border = border_all
                col_idx += 1

                if pnum in break_after_set:
                    b_cell = ws3.cell(row=row_num, column=col_idx, value="LUNCH / BREAK")
                    b_cell.font = bold_font
                    b_cell.fill = break_fill
                    b_cell.alignment = align_center
                    b_cell.border = border_all
                    col_idx += 1

            row_num += 1
        row_num += 2

    # --- SHEET 4: COURSE DETAILS ---
    ws4 = wb.create_sheet(title="Course Details")
    ws4.views.sheetView[0].showGridLines = True
    ws4.cell(row=1, column=1, value="COURSE DETAILS SUMMARY").font = title_font
    ws4.cell(row=1, column=1).fill = title_fill
    ws4.cell(row=1, column=1).alignment = align_center
    ws4.merge_cells(start_row=1, start_column=1, end_row=2, end_column=6)

    c_headers = ["Class", "Subject Code", "Subject Name", "Type", "Faculty Member(s)", "Required Periods/Wk"]
    for col_idx, ch in enumerate(c_headers, start=1):
        c_cell = ws4.cell(row=3, column=col_idx, value=ch)
        c_cell.font = header_font
        c_cell.fill = header_fill
        c_cell.alignment = align_center
        c_cell.border = border_all

    row_num = 4
    all_reqs = database.get_class_subject_requirements(admin_id)
    for req in all_reqs:
        fac_str = ", ".join(faculty_map.get((req['class_id'], req['subject_id']), ["Unassigned"]))
        row_vals = [req['class_name'], req['subject_code'], req['subject_name'], req['subject_type'], fac_str, req['periods_per_week']]
        for col_idx, val in enumerate(row_vals, start=1):
            c_cell = ws4.cell(row=row_num, column=col_idx, value=val)
            c_cell.font = cell_font
            c_cell.alignment = align_left if col_idx in [1,3,5] else align_center
            c_cell.border = border_all
        row_num += 1

    # --- SHEET 5: GENERATION SUMMARY ---
    ws5 = wb.create_sheet(title="Generation Summary")
    ws5.views.sheetView[0].showGridLines = True
    ws5.cell(row=1, column=1, value="TIMETABLE GENERATION SUMMARY").font = title_font
    ws5.cell(row=1, column=1).fill = title_fill
    ws5.cell(row=1, column=1).alignment = align_center
    ws5.merge_cells(start_row=1, start_column=1, end_row=2, end_column=2)

    summary_data = [
        ("Application Name", "Optimized Time Table with AI"),
        ("Institution Name", settings['college_name']),
        ("Academic Year", settings['academic_year']),
        ("Department", settings['department']),
        ("Generation Timestamp", current_run['run_timestamp'] if current_run else "N/A"),
        ("Optimization Engine", "Google OR-Tools CP-SAT Solver"),
        ("Solver Status", current_run['solver_status'] if current_run else "N/A"),
        ("Objective Score Value", current_run['objective_value'] if current_run else "N/A"),
        ("Overall Quality Score", f"{current_run['quality_score']}/100" if current_run else "N/A"),
        ("Generation Status", current_run['status'] if current_run else "N/A"),
        ("Total Scheduled Sessions", len(entries))
    ]
    row_num = 4
    for k, v in summary_data:
        k_cell = ws5.cell(row=row_num, column=1, value=k)
        k_cell.font = bold_font
        k_cell.fill = accent_fill
        k_cell.border = border_all
        k_cell.alignment = align_left

        v_cell = ws5.cell(row=row_num, column=2, value=str(v))
        v_cell.font = cell_font
        v_cell.border = border_all
        v_cell.alignment = align_left
        row_num += 1

    # Adjust widths for all sheets
    for ws in wb.worksheets:
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                if cell.value:
                    lines = str(cell.value).split('\n')
                    for line in lines:
                        if len(line) > max_len:
                            max_len = len(line)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 15)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def generate_excel_view_export(admin_id: int, run_id: int, view: str) -> bytes:
    """Return a focused Excel workbook containing only one timetable view.
    view: class, teacher, or room.
    """
    view_map = {
        "class": "Class Timetables",
        "teacher": "Teacher Timetables",
        "room": "Room & Lab Timetables",
    }
    if view not in view_map:
        raise ValueError("view must be class, teacher, or room")
    source = generate_excel_export(admin_id, run_id)
    wb = openpyxl.load_workbook(io.BytesIO(source))
    target = view_map[view]
    for ws in list(wb.worksheets):
        if ws.title != target:
            wb.remove(ws)
    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out.getvalue()
