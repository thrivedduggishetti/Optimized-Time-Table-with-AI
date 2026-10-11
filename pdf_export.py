import io
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import database

def generate_pdf_export(admin_id: int, run_id: int, target_class_id: int = None) -> bytes:
    """
    Generates a high-quality landscape PDF document using ReportLab.
    If target_class_id is specified, exports single class timetable.
    If target_class_id is None, exports full timetable bundle.
    Returns raw PDF bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=0.4 * inch,
        leftMargin=0.4 * inch,
        topMargin=0.4 * inch,
        bottomMargin=0.4 * inch
    )

    story = []
    styles = getSampleStyleSheet()

    # Custom Styles
    app_title_style = ParagraphStyle(
        'AppTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#1E1B4B'), # Deep Navy
        alignment=1 # Center
    )

    institution_style = ParagraphStyle(
        'Institution',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#4338CA'), # Indigo
        alignment=1
    )

    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#64748B'),
        alignment=1
    )

    section_heading = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=15,
        textColor=colors.HexColor('#0F172A')
    )

    cell_style = ParagraphStyle(
        'CellText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        alignment=1
    )

    cell_bold = ParagraphStyle(
        'CellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        alignment=1
    )

    header_cell_style = ParagraphStyle(
        'HeaderCell',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        textColor=colors.white,
        alignment=1
    )

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

    break_after_set = {b['after_period'] for b in breaks}

    target_classes = [c for c in classes if c['id'] == target_class_id] if target_class_id else classes

    for idx, c in enumerate(target_classes):
        if idx > 0:
            story.append(PageBreak())

        # Document Header
        story.append(Paragraph("OPTIMIZED TIME TABLE WITH AI", app_title_style))
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"{settings['college_name']} — {settings['department']}", institution_style))
        story.append(Paragraph(f"Academic Year: {settings['academic_year']} | Quality Score: {current_run['quality_score'] if current_run else 'N/A'}/100", subtitle_style))
        story.append(Spacer(1, 10))

        # Class Info Banner
        story.append(Paragraph(f"<b>Class:</b> {c['name']} | <b>Strength:</b> {c['student_strength']} Students | <b>Class Teacher:</b> {c.get('class_teacher', 'N/A')}", section_heading))
        story.append(Spacer(1, 8))

        # Build Timetable Table
        c_entries = [e for e in entries if e['class_id'] == c['id']]
        entry_grid = {(e['day_name'], e['period_number']): e for e in c_entries}

        headers = [Paragraph("<b>Day</b>", header_cell_style)]
        for p in periods:
            headers.append(Paragraph(f"<b>{p['period_name']}</b><br/>{p['start_time']}-{p['end_time']}", header_cell_style))
            if p['period_number'] in break_after_set:
                headers.append(Paragraph("<b>BREAK</b>", header_cell_style))

        table_data = [headers]

        for d in days:
            row = [Paragraph(f"<b>{d}</b>", cell_bold)]
            for p in periods:
                pnum = p['period_number']
                e = entry_grid.get((d, pnum))
                if e:
                    sname = e['subject_name']
                    scode = e['subject_code']
                    fac_str = ", ".join(faculty_map.get((c['id'], e['subject_id']), ["Unassigned"]))
                    res_name = rooms_dict.get(e['resource_id'], {}).get('name') if e['resource_type'] == 'ROOM' else labs_dict.get(e['resource_id'], {}).get('name')
                    cell_text = f"<b>{sname}</b> ({scode})<br/>{fac_str}<br/><i>{res_name}</i>"
                    row.append(Paragraph(cell_text, cell_style))
                else:
                    row.append(Paragraph("— Free —", cell_style))

                if pnum in break_after_set:
                    row.append(Paragraph("☕", cell_bold))

            table_data.append(row)

        col_count = len(headers)
        col_width = (10.0 * inch) / col_count

        t_table = Table(table_data, colWidths=[col_width] * col_count)
        t_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#312E81')), # Dark Indigo
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F8FAFC')])
        ]))
        story.append(t_table)
        story.append(Spacer(1, 14))

        # Course Details Table
        story.append(Paragraph("<b>Course & Faculty Allocation Details</b>", section_heading))
        story.append(Spacer(1, 4))
        reqs = database.get_class_subject_requirements(admin_id, class_id=c['id'])
        if reqs:
            cd_headers = [
                Paragraph("<b>Code</b>", header_cell_style),
                Paragraph("<b>Subject Name</b>", header_cell_style),
                Paragraph("<b>Type</b>", header_cell_style),
                Paragraph("<b>Faculty Member(s)</b>", header_cell_style),
                Paragraph("<b>Periods/Wk</b>", header_cell_style)
            ]
            cd_data = [cd_headers]
            for req in reqs:
                fac_str = ", ".join(faculty_map.get((c['id'], req['subject_id']), ["Unassigned"]))
                cd_data.append([
                    Paragraph(req['subject_code'], cell_bold),
                    Paragraph(req['subject_name'], cell_style),
                    Paragraph(req['subject_type'], cell_style),
                    Paragraph(fac_str, cell_style),
                    Paragraph(str(req['periods_per_week']), cell_style)
                ])
            cd_table = Table(cd_data, colWidths=[1.2*inch, 3.5*inch, 1.0*inch, 3.3*inch, 1.0*inch])
            cd_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#4338CA')),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE')
            ]))
            story.append(cd_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def generate_personnel_pdf_export(admin_id: int, run_id: int, view: str) -> bytes:
    """Generate teacher-wise or room/lab-wise timetable PDF."""
    if view not in {"teacher", "room"}:
        raise ValueError("view must be teacher or room")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(letter), rightMargin=0.35*inch,
        leftMargin=0.35*inch, topMargin=0.35*inch, bottomMargin=0.35*inch
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle('pv_title', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=17, alignment=1, textColor=colors.HexColor('#1E1B4B'))
    inst = ParagraphStyle('pv_inst', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=12, alignment=1, textColor=colors.HexColor('#4338CA'))
    sub = ParagraphStyle('pv_sub', parent=styles['Normal'], fontSize=9, alignment=1, textColor=colors.HexColor('#64748B'))
    head = ParagraphStyle('pv_head', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.white, alignment=1)
    cell = ParagraphStyle('pv_cell', parent=styles['Normal'], fontSize=7, leading=9, alignment=1)
    bold = ParagraphStyle('pv_bold', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7, leading=9, alignment=1)

    entries = database.get_timetable_entries_by_run(admin_id, run_id)
    runs = database.get_timetable_runs(admin_id)
    run = next((r for r in runs if r['id'] == run_id), None)
    settings = database.get_admin_settings(admin_id)
    classes = database.get_classes(admin_id)
    teachers = database.get_teachers(admin_id)
    rooms = database.get_rooms(admin_id)
    labs = database.get_labs(admin_id)
    days = [d['day_name'] for d in database.get_working_days(admin_id) if d['is_active']]
    periods = database.get_periods(admin_id)
    breaks = database.get_breaks(admin_id)
    assignments = database.get_teacher_assignments(admin_id)
    class_map = {c['id']: c for c in classes}
    teacher_map = {t['id']: t for t in teachers}
    room_map = {r['id']: r for r in rooms}
    lab_map = {l['id']: l for l in labs}
    faculty_map = {}
    for a in assignments:
        faculty_map.setdefault((a['class_id'], a['subject_id']), []).append(
            teacher_map.get(a['teacher_id'], {}).get('name', f"Teacher #{a['teacher_id']}")
        )
    break_after = {b['after_period'] for b in breaks}

    if view == 'teacher':
        entities = [(t['id'], t['name'], 'teacher') for t in teachers]
    else:
        entities = [(r['id'], r['name'], 'ROOM') for r in rooms] + [(l['id'], l['name'], 'LAB') for l in labs]

    story = []
    for idx, (entity_id, entity_name, entity_type) in enumerate(entities):
        if idx:
            story.append(PageBreak())
        story += [Paragraph('OPTIMIZED TIME TABLE WITH AI', title), Spacer(1, 3),
                  Paragraph(settings.get('college_name') or 'Institution Not Configured', inst),
                  Paragraph(f"Academic Year: {settings.get('academic_year') or 'Not configured'} | Quality Score: {run['quality_score'] if run else 'N/A'}/100", sub), Spacer(1, 8)]
        label = 'Faculty' if view == 'teacher' else ('Classroom' if entity_type == 'ROOM' else 'Laboratory')
        story.append(Paragraph(f"<b>{label}:</b> {entity_name}", ParagraphStyle('entity', parent=styles['Heading2'], fontSize=12)))
        story.append(Spacer(1, 6))

        if view == 'teacher':
            relevant = []
            for e in entries:
                names = faculty_map.get((e['class_id'], e['subject_id']), [])
                if any(n == entity_name for n in names):
                    relevant.append(e)
        else:
            relevant = [e for e in entries if e['resource_type'] == entity_type and e['resource_id'] == entity_id]
        grid = {(e['day_name'], e['period_number']): e for e in relevant}
        headers = [Paragraph('<b>Day</b>', head)]
        for p in periods:
            headers.append(Paragraph(f"<b>{p['period_name']}</b><br/>{p['start_time']}-{p['end_time']}", head))
            if p['period_number'] in break_after:
                headers.append(Paragraph('<b>BREAK</b>', head))
        data = [headers]
        for d in days:
            row = [Paragraph(f'<b>{d}</b>', bold)]
            for p in periods:
                e = grid.get((d, p['period_number']))
                if e:
                    cname = class_map.get(e['class_id'], {}).get('name', '')
                    fac = ', '.join(faculty_map.get((e['class_id'], e['subject_id']), ['Unassigned']))
                    if e['resource_type'] == 'ROOM':
                        resource = room_map.get(e['resource_id'], {}).get('name', '')
                    else:
                        resource = lab_map.get(e['resource_id'], {}).get('name', '')
                    text = f"<b>{e['subject_name']}</b> ({e['subject_code']})<br/>Class: {cname}<br/>{fac}<br/><i>{resource}</i>"
                else:
                    text = '— Free —'
                row.append(Paragraph(text, cell))
                if p['period_number'] in break_after:
                    row.append(Paragraph('BREAK', bold))
            data.append(row)
        col_count = len(headers)
        col_width = (10.2 * inch) / col_count
        table = Table(data, colWidths=[col_width] * col_count)
        table.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#312E81')),
            ('ALIGN',(0,0),(-1,-1),'CENTER'), ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('GRID',(0,0),(-1,-1),0.5,colors.HexColor('#CBD5E1')),
            ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white, colors.HexColor('#F8FAFC')])
        ]))
        story.append(table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
