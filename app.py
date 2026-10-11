import streamlit as st
import pandas as pd
import database
import auth
import validation
import timetable_engine
import timetable_views
import excel_export
import pdf_export
import demo_data
import quality_score


# Page Configuration
st.set_page_config(
    page_title="Optimized Time Table with AI",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize Database Schema
database.init_db()

# --- AUTHENTICATION CHECK & ROUTING ---
if not auth.is_authenticated():
    st.markdown("<h1 style='text-align: center; color: #6366F1;'>🎓 OPTIMIZED TIME TABLE WITH AI</h1>", unsafe_allow_html=True)

    st.markdown("<p style='text-align: center; color: #94A3B8;'>AI-Powered College Timetable Generation & Resource Optimization System</p>", unsafe_allow_html=True)
    st.markdown("---")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        auth_mode = st.radio("Choose Action:", ["Login to Administrator Account", "Create Administrator Account"], horizontal=True)

        if auth_mode == "Login to Administrator Account":
            st.subheader("🔑 Administrator Login")
            with st.form("login_form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Login", use_container_width=True)

                if submitted:
                    success, msg, admin_dict = auth.authenticate_admin(username, password)
                    if success:
                        auth.login_session(admin_dict)
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

        else:
            st.subheader("📝 Register New Administrator Account")
            with st.form("register_form"):
                reg_username = st.text_input("New Username")
                reg_password = st.text_input("Password (min 6 characters)", type="password")
                reg_confirm = st.text_input("Confirm Password", type="password")
                reg_submitted = st.form_submit_button("Create Administrator Account", use_container_width=True)

                if reg_submitted:
                    success, msg = auth.register_admin(reg_username, reg_password, reg_confirm)
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)

    st.stop()

# --- AUTHENTICATED USER SESSION ---
admin_id = auth.get_current_admin_id()
admin_username = auth.get_current_admin_username()
admin_settings = database.get_admin_settings(admin_id)

# Sidebar Header & Navigation
st.sidebar.markdown(f"### 🎓 Optimized Time Table with AI")

st.sidebar.markdown(f"**Admin:** `{admin_username}`")

_institution = (admin_settings.get('college_name') or '').strip()
if _institution:
    st.sidebar.markdown(f"**Institution:** {_institution}")
else:
    st.sidebar.markdown("**Institution:** _Not configured_")
st.sidebar.markdown("---")

nav_menu_list = [
    "Dashboard",
    "Academic Setup",
    "Schedule Setup",
    "Teacher Availability",
    "Resources",
    "Constraints",
    "Generate Timetable",
    "Timetable Views",
    "Quality Analysis",
    "Generation History",
    "Export",
    "Settings",
    "Logout"
]

if "nav_selection" not in st.session_state:
    st.session_state["nav_selection"] = "Dashboard"

if st.session_state.get('nav_to_gen'):
    st.session_state["nav_selection"] = "Generate Timetable"
    st.session_state['nav_to_gen'] = False

nav_option = st.sidebar.radio(
    "Navigation Menu",
    nav_menu_list,
    key="nav_selection"
)


st.sidebar.markdown("---")
if st.sidebar.button("🚀 Load Demo Data", use_container_width=True, help="Populate test college data for quick evaluation"):
    success, d_msg = demo_data.load_demo_data_for_admin(admin_id)
    if success:
        st.sidebar.success(d_msg)
        st.rerun()
    else:
        st.sidebar.error(d_msg)

# ============================================================
# 1. DASHBOARD
# ============================================================
if nav_option == "Dashboard":
    st.title("Optimized Time Table with AI")
    st.subheader(f"Welcome, Administrator **{admin_username}** 👋")

    # Metrics Summary Cards
    c1, c2, c3, c4, c5 = st.columns(5)
    classes = database.get_classes(admin_id)
    teachers = database.get_teachers(admin_id)
    subjects = database.get_subjects(admin_id)
    rooms = database.get_rooms(admin_id)
    labs = database.get_labs(admin_id)
    latest_run = database.get_latest_timetable_run(admin_id)

    c1.metric("Classes", len(classes))
    c2.metric("Faculty Members", len(teachers))
    c3.metric("Subjects", len(subjects))
    c4.metric("Rooms & Labs", len(rooms) + len(labs))
    c5.metric("Quality Score", f"{latest_run['quality_score']}/100" if latest_run else "N/A")

    st.markdown("---")

    col_left, col_right = st.columns([3, 2])
    with col_left:
        st.subheader("🔄 System Workflow")
        st.info("""
        **1. Academic Setup** → Configure Classes, Faculty Members, Subjects, and Faculty Assignments.  
        **2. Schedule Setup** → Define Working Days, Period Timings, and Lunch/Break slots.  
        **3. Resource Setup** → Configure Classrooms, Laboratories, and Lab Subject Mappings.  
        **4. Constraint Setup** → Adjust mandatory Hard Rules and soft optimization weights.  
        **5. Validation & AI Optimization** → Validate inputs & invoke Google OR-Tools CP-SAT model.  
        **6. Timetable & Quality Analysis** → Inspect Class/Teacher/Room timetables & quality scores.  
        **7. Excel & PDF Export** → Export production-grade timetables.
        """)

    with col_right:
        st.subheader("⚡ Quick Actions")
        if st.button("▶️ Generate Timetable Now", use_container_width=True, type="primary"):
            st.session_state['nav_to_gen'] = True
            st.rerun()

        if latest_run:
            st.success(f"Latest Successful Run: ID #{latest_run['id']} on {latest_run['run_timestamp']} ({latest_run['solver_status']})")
        else:
            st.warning("No timetable generated yet. Populate setup data or click 'Load Demo Data' to get started.")

# ============================================================
# 2. ACADEMIC SETUP
# ============================================================
elif nav_option == "Academic Setup":
    st.title("Academic Setup")
    sub_tab = st.tabs(["Classes / Sections", "Teachers / Faculty", "Subjects", "Class-Subject Requirements", "Faculty Assignment"])

    # --- CLASSES ---
    with sub_tab[0]:
        st.subheader("Manage Classes & Sections")
        with st.expander("➕ Add New Class / Section", expanded=False):
            with st.form("add_class_form"):
                c_name = st.text_input("Class Name (e.g. III B.Tech AIML - A)")
                c_ayear = st.text_input("Academic Year", value=admin_settings.get('academic_year', '2026-27'))
                c_year = st.selectbox("Year", ["1st Year", "2nd Year", "3rd Year", "4th Year"])
                c_sem = st.selectbox("Semester", ["1st Semester", "2nd Semester"])
                c_branch = st.text_input("Branch", value=admin_settings.get('branch', 'AIML'))
                c_sec = st.text_input("Section", value="A")
                c_strength = st.number_input("Student Strength", min_value=1, value=60)
                c_teacher = st.text_input("Class Teacher Name")

                if st.form_submit_button("Save Class"):
                    if c_name:
                        database.add_class(admin_id, c_name, c_ayear, c_year, c_sem, c_branch, c_sec, c_strength, c_teacher)
                        st.success(f"Class '{c_name}' added successfully!")
                        st.rerun()

        classes_data = database.get_classes(admin_id)
        if classes_data:
            df_c = pd.DataFrame(classes_data)
            st.dataframe(df_c[['id', 'name', 'academic_year', 'year', 'semester', 'branch', 'section', 'student_strength', 'class_teacher']], use_container_width=True)

            del_cid = st.selectbox("Select Class to Delete:", [c['id'] for c in classes_data], format_func=lambda x: next(c['name'] for c in classes_data if c['id'] == x))
            if st.button("🗑️ Delete Class", type="secondary"):
                database.delete_class(admin_id, del_cid)
                st.success("Class deleted.")
                st.rerun()

    # --- TEACHERS ---
    with sub_tab[1]:
        st.subheader("Manage Faculty Members")
        with st.expander("➕ Add Faculty Member", expanded=False):
            with st.form("add_teacher_form", clear_on_submit=True):
                t_name = st.text_input("Teacher Name (e.g. Dr. Rituparna Roy)")
                t_email = st.text_input("Email")
                t_max = st.number_input("Max Periods Per Day", min_value=1, max_value=10, value=6)

                if st.form_submit_button("Save Teacher"):
                    if t_name:
                        database.add_teacher(admin_id, t_name, t_email, t_max)
                        st.success(f"Teacher '{t_name}' added!")
                        st.rerun()

        teachers_data = database.get_teachers(admin_id)
        if teachers_data:
            st.dataframe(pd.DataFrame(teachers_data)[['id', 'name', 'email', 'max_periods_per_day']], use_container_width=True)
            del_tid = st.selectbox("Select Faculty to Delete:", [t['id'] for t in teachers_data], format_func=lambda x: next(t['name'] for t in teachers_data if t['id'] == x))
            if st.button("🗑️ Delete Faculty", type="secondary"):
                database.delete_teacher(admin_id, del_tid)
                st.success("Faculty member deleted.")
                st.rerun()

    # --- SUBJECTS ---
    with sub_tab[2]:
        st.subheader("Manage Subjects")
        with st.expander("➕ Add Subject", expanded=False):
            with st.form("add_subject_form"):
                s_code = st.text_input("Subject Code (e.g. CN)")
                s_name = st.text_input("Subject Name (e.g. Computer Networks)")
                s_type = st.selectbox("Subject Type", ["Theory", "Lab"])
                s_def_p = st.number_input("Default Periods Per Week", min_value=1, value=3)

                if st.form_submit_button("Save Subject"):
                    if s_code and s_name:
                        try:
                            database.add_subject(admin_id, s_code, s_name, s_type, s_def_p)
                            st.success(f"Subject '{s_name}' added!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error adding subject: {e}")

        subjects_data = database.get_subjects(admin_id)
        if subjects_data:
            st.dataframe(pd.DataFrame(subjects_data)[['id', 'code', 'name', 'type', 'default_periods_per_week']], use_container_width=True)
            del_sid = st.selectbox("Select Subject to Delete:", [s['id'] for s in subjects_data], format_func=lambda x: next(s['name'] for s in subjects_data if s['id'] == x))
            if st.button("🗑️ Delete Subject", type="secondary"):
                database.delete_subject(admin_id, del_sid)
                st.success("Subject deleted.")
                st.rerun()

    # --- CLASS-SUBJECT REQUIREMENTS ---
    with sub_tab[3]:
        st.subheader("Class-Subject Period Requirements")
        st.caption("Configure how many weekly periods each class requires for each subject.")
        classes_data = database.get_classes(admin_id)
        subjects_data = database.get_subjects(admin_id)

        if classes_data and subjects_data:
            with st.form("add_req_form"):
                sel_c = st.selectbox("Select Class", classes_data, format_func=lambda c: c['name'])
                sel_s = st.selectbox("Select Subject", subjects_data, format_func=lambda s: f"{s['name']} ({s['code']}) [{s['type']}]")
                req_p = st.number_input("Required Periods / Week", min_value=1, max_value=10, value=3)
                consec_p = st.number_input("Consecutive Periods Block", min_value=1, max_value=4, value=2 if sel_s['type'] == 'Lab' else 1)

                if st.form_submit_button("Assign Subject Requirement"):
                    database.add_class_subject_requirement(admin_id, sel_c['id'], sel_s['id'], req_p, consec_p)
                    st.success(f"Requirement saved for '{sel_c['name']}'!")
                    st.rerun()

        reqs_data = database.get_class_subject_requirements(admin_id)
        if reqs_data:
            st.dataframe(pd.DataFrame(reqs_data)[['id', 'class_name', 'subject_code', 'subject_name', 'subject_type', 'periods_per_week', 'consecutive_periods']], use_container_width=True)
            del_rid = st.selectbox("Delete Requirement:", [r['id'] for r in reqs_data], format_func=lambda x: next(f"{r['class_name']} - {r['subject_name']}" for r in reqs_data if r['id'] == x))
            if st.button("🗑️ Remove Requirement"):
                database.delete_class_subject_requirement(admin_id, del_rid)
                st.rerun()

    # --- FACULTY ASSIGNMENT ---
    with sub_tab[4]:
        st.subheader("Faculty Assignment (Teacher → Subject)")
        st.caption("Explicitly assign faculty members to teach subjects for each class.")

        reqs_data = database.get_class_subject_requirements(admin_id)
        teachers_data = database.get_teachers(admin_id)

        if reqs_data and teachers_data:
            with st.form("assign_faculty_form"):
                sel_req = st.selectbox("Select Class & Subject Requirement:", reqs_data, format_func=lambda r: f"{r['class_name']} → {r['subject_name']} ({r['subject_type']})")
                sel_t = st.selectbox("Select Faculty Member:", teachers_data, format_func=lambda t: t['name'])
                role = st.selectbox("Role", ["PRIMARY", "CO_TEACHER"])

                if st.form_submit_button("Assign Faculty"):
                    database.add_teacher_assignment(admin_id, sel_req['class_id'], sel_req['subject_id'], sel_t['id'], role)
                    st.success("Faculty assigned successfully!")
                    st.rerun()

        assignments_data = database.get_teacher_assignments(admin_id)
        if assignments_data:
            st.dataframe(pd.DataFrame(assignments_data)[['id', 'class_name', 'subject_code', 'subject_name', 'teacher_name', 'role']], use_container_width=True)
            del_aid = st.selectbox("Delete Faculty Assignment:", [a['id'] for a in assignments_data], format_func=lambda x: next(f"{a['class_name']} - {a['subject_name']} ({a['teacher_name']})" for a in assignments_data if a['id'] == x))
            if st.button("🗑️ Remove Faculty Assignment"):
                database.delete_teacher_assignment(admin_id, del_aid)
                st.rerun()

# ============================================================
# 3. SCHEDULE SETUP
# ============================================================
elif nav_option == "Schedule Setup":
    st.title("Schedule Setup")
    tab_d, tab_p, tab_b = st.tabs(["Working Days", "Period Timings", "Lunch / Breaks"])

    with tab_d:
        st.subheader("Working Days")
        days = database.get_working_days(admin_id)
        if days:
            st.dataframe(pd.DataFrame(days)[['id', 'day_name', 'day_order', 'is_active']], use_container_width=True)

    with tab_p:
        st.subheader("Period Timings")
        periods = database.get_periods(admin_id)
        if periods:
            st.dataframe(pd.DataFrame(periods)[['id', 'period_number', 'period_name', 'start_time', 'end_time', 'is_active']], use_container_width=True)

    with tab_b:
        st.subheader("Lunch & Break Slots")
        breaks = database.get_breaks(admin_id)
        if breaks:
            st.dataframe(pd.DataFrame(breaks)[['id', 'break_name', 'start_time', 'end_time', 'after_period']], use_container_width=True)

# ============================================================
# 4. TEACHER AVAILABILITY
# ============================================================
elif nav_option == "Teacher Availability":
    st.title("Teacher Availability Grid")
    teachers = database.get_teachers(admin_id)
    days = [d['day_name'] for d in database.get_working_days(admin_id) if d['is_active']]
    periods = database.get_periods(admin_id)

    if not teachers:
        st.warning("No teachers configured.")
    else:
        selected_tid = st.selectbox("Select Teacher:", teachers, format_func=lambda t: t['name'])
        tid = selected_tid['id']

        av_data = database.get_teacher_availability(admin_id, tid)
        av_map = {(a['day_name'], a['period_number']): bool(a['is_available']) for a in av_data}

        st.write(f"Configure availability matrix for **{selected_tid['name']}**:")
        st.caption("Check the box if the teacher is AVAILABLE for that slot. Uncheck if UNAVAILABLE.")

        matrix_rows = []
        with st.form("availability_matrix_form"):
            for d in days:
                cols = st.columns(len(periods) + 1)
                cols[0].markdown(f"**{d}**")
                for p_idx, p in enumerate(periods, start=1):
                    pnum = p['period_number']
                    is_av = av_map.get((d, pnum), True)
                    val = cols[p_idx].checkbox(f"{p['period_name']}", value=is_av, key=f"av_{tid}_{d}_{pnum}")
                    if not val:
                        matrix_rows.append((d, pnum, 0))
                    else:
                        matrix_rows.append((d, pnum, 1))

            if st.form_submit_button("Save Teacher Availability Matrix"):
                for d, pnum, is_a in matrix_rows:
                    database.set_teacher_availability(admin_id, tid, d, pnum, is_a)
                st.success(f"Availability updated for {selected_tid['name']}!")
                st.rerun()

# ============================================================
# 5. RESOURCES
# ============================================================
elif nav_option == "Resources":
    st.title("Resource Setup (Classrooms & Laboratories)")
    tab_r, tab_l, tab_lr = st.tabs(["Classrooms", "Laboratories", "Lab Requirements"])

    with tab_r:
        st.subheader("Manage Classrooms")
        with st.form("add_room_form"):
            r_name = st.text_input("Room Name (e.g. E314)")
            r_type = st.text_input("Room Type", value="Classroom")
            r_cap = st.number_input("Capacity", min_value=1, value=60)
            if st.form_submit_button("Add Classroom"):
                if r_name:
                    database.add_room(admin_id, r_name, r_type, r_cap)
                    st.success("Classroom added!")
                    st.rerun()

        rooms = database.get_rooms(admin_id)
        if rooms:
            st.dataframe(pd.DataFrame(rooms)[['id', 'name', 'room_type', 'capacity']], use_container_width=True)

    with tab_l:
        st.subheader("Manage Laboratories")
        with st.form("add_lab_form"):
            l_name = st.text_input("Lab Name (e.g. AI Lab)")
            l_type = st.text_input("Lab Type", value="AI Laboratory")
            l_cap = st.number_input("Capacity", min_value=1, value=40)
            if st.form_submit_button("Add Laboratory"):
                if l_name:
                    database.add_lab(admin_id, l_name, l_type, l_cap)
                    st.success("Laboratory added!")
                    st.rerun()

        labs = database.get_labs(admin_id)
        if labs:
            st.dataframe(pd.DataFrame(labs)[['id', 'name', 'lab_type', 'capacity']], use_container_width=True)

    with tab_lr:
        st.subheader("Lab Requirements Mapping")
        subjects = [s for s in database.get_subjects(admin_id) if s['type'] == 'Lab']
        labs = database.get_labs(admin_id)

        if subjects and labs:
            with st.form("add_lab_req_form"):
                sel_s = st.selectbox("Select Lab Subject:", subjects, format_func=lambda s: f"{s['name']} ({s['code']})")
                sel_l = st.selectbox("Select Target Laboratory:", labs, format_func=lambda l: f"{l['name']} (Cap: {l['capacity']})")
                if st.form_submit_button("Map Subject → Laboratory"):
                    database.add_lab_requirement(admin_id, sel_s['id'], sel_l['id'])
                    st.success("Lab mapping saved!")
                    st.rerun()

        l_reqs = database.get_lab_requirements(admin_id)
        if l_reqs:
            st.dataframe(pd.DataFrame(l_reqs)[['id', 'subject_code', 'subject_name', 'lab_name']], use_container_width=True)

# ============================================================
# 6. CONSTRAINTS
# ============================================================
elif nav_option == "Constraints":
    st.title("Constraint Configuration")
    tab_h, tab_s = st.tabs(["Hard Constraints", "Soft Constraints"])

    with tab_h:
        st.subheader("Hard Constraints Configuration")
        h_rules = database.get_hard_constraints(admin_id)
        for h in h_rules:
            c1, c2 = st.columns([4, 1])
            is_mand = bool(h['is_mandatory'])
            c1.markdown(f"**{h['code']} - {h['name']}** {'*(Mandatory Core Rule)*' if is_mand else ''}\n\n_{h['description']}_")
            new_en = c2.checkbox("Enabled", value=bool(h['is_enabled']), disabled=is_mand, key=f"hc_{h['id']}")
            if new_en != bool(h['is_enabled']):
                database.update_hard_constraint(admin_id, h['id'], int(new_en))
                st.rerun()

    with tab_s:
        st.subheader("Soft Constraints & Optimization Weights")
        s_rules = database.get_soft_constraints(admin_id)
        for s in s_rules:
            c1, c2, c3 = st.columns([3, 1, 1])
            c1.markdown(f"**{s['code']} - {s['name']}**\n\n_{s['description']}_")
            new_en = c2.checkbox("Enabled", value=bool(s['is_enabled']), key=f"sc_en_{s['id']}")
            new_wt = c3.number_input("Weight (1-10)", min_value=1, max_value=10, value=int(s['weight']), key=f"sc_wt_{s['id']}")
            if new_en != bool(s['is_enabled']) or new_wt != int(s['weight']):
                database.update_soft_constraint(admin_id, s['id'], int(new_en), new_wt)
                st.rerun()

# ============================================================
# 7. GENERATE TIMETABLE
# ============================================================
elif nav_option == "Generate Timetable":
    st.title("⚡ AI Timetable Generation Engine")
    st.caption("Powered by Google OR-Tools CP-SAT Solver")

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🔍 Validate Configuration", use_container_width=True):
            is_v, errs = validation.validate_input_configuration(admin_id)
            if is_v:
                st.success("✅ Configuration is valid! Ready for CP-SAT optimization.")
            else:
                st.error("❌ Configuration validation failed:")
                for e in errs:
                    st.write(f"• {e}")

    with col_btn2:
        if st.button("🚀 Run AI Solver & Generate Timetable", type="primary", use_container_width=True):
            with st.spinner("Building CP-SAT Model & Solving Constraints..."):
                success, msg, res = timetable_engine.generate_timetable(admin_id)
                if success:
                    st.balloons()
                    st.success(f"🎉 {msg}")
                    st.metric("Overall Quality Score", f"{res['quality_score']}/100")
                    st.session_state['latest_generated_run_id'] = res['run_id']
                else:
                    st.error(f"❌ Generation Failed: {msg}")
                    if 'errors' in res:
                        for err in res['errors']:
                            st.write(f"• {err}")

# ============================================================
# 8. TIMETABLE VIEWS
# ============================================================
elif nav_option == "Timetable Views":
    st.title("Interactive Timetable Views")
    latest_run = database.get_latest_timetable_run(admin_id)
    if not latest_run:
        st.warning("No generated timetable found. Please generate a timetable first.")
    else:
        st.info(f"Displaying Timetable Run #{latest_run['id']} (Generated: {latest_run['run_timestamp']})")
        timetable_views.render_timetable_views(admin_id, latest_run['id'])

# ============================================================
# 9. QUALITY ANALYSIS
# ============================================================
elif nav_option == "Quality Analysis":
    st.title("Timetable Quality Analysis")
    latest_run = database.get_latest_timetable_run(admin_id)
    if not latest_run:
        st.warning("No timetable available for quality analysis.")
    else:
        entries = database.get_timetable_entries_by_run(admin_id, latest_run['id'])
        q_res = quality_score.calculate_quality_score(admin_id, entries)

        st.metric("Overall Quality Score", f"{q_res['overall_score']} / 100")
        st.markdown("---")
        st.subheader("Metric Score Breakdown")

        bd = q_res['breakdown']
        st.write(f"• **Subject Distribution Score:** {bd['subject_distribution']} / 25")
        st.write(f"• **Teacher Workload Balance Score:** {bd['teacher_workload_balance']} / 20")
        st.write(f"• **Class Idle Gap Score:** {bd['class_gap_score']} / 20")
        st.write(f"• **Resource Capacity Utilization Score:** {bd['resource_utilization']} / 15")
        st.write(f"• **Soft Constraint Satisfaction Score:** {bd['soft_constraint_satisfaction']} / 20")

# ============================================================
# 10. GENERATION HISTORY
# ============================================================
elif nav_option == "Generation History":
    st.title("Timetable Generation History")
    runs = database.get_timetable_runs(admin_id)
    if not runs:
        st.info("No generation runs recorded yet.")
    else:
        st.dataframe(pd.DataFrame(runs), use_container_width=True)

# ============================================================
# 11. EXPORT
# ============================================================
elif nav_option == "Export":
    st.title("Export Timetables")
    latest_run = database.get_latest_timetable_run(admin_id)
    if not latest_run:
        st.warning("No timetable run available for export.")
    else:
        run_id = latest_run['id']
        st.subheader(f"Exporting Timetable Run #{run_id}")

        st.markdown("### 📥 Download Timetable Views")
        st.caption("Download the class-wise, teacher-wise, or room/lab-wise timetable separately. A full multi-sheet workbook and full PDF are also available below.")

        e1, e2, e3 = st.columns(3)
        with e1:
            st.markdown("**📚 Class-wise**")
            st.download_button(
                "⬇️ Excel",
                data=excel_export.generate_excel_view_export(admin_id, run_id, "class"),
                file_name=f"Classwise_Timetable_Run_{run_id}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key=f"class_excel_{run_id}"
            )
            st.download_button(
                "⬇️ PDF",
                data=pdf_export.generate_pdf_export(admin_id, run_id),
                file_name=f"Classwise_Timetable_Run_{run_id}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key=f"class_pdf_{run_id}"
            )

        with e2:
            st.markdown("**👨‍🏫 Teacher-wise**")
            st.download_button(
                "⬇️ Excel",
                data=excel_export.generate_excel_view_export(admin_id, run_id, "teacher"),
                file_name=f"Teacherwise_Timetable_Run_{run_id}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key=f"teacher_excel_{run_id}"
            )
            st.download_button(
                "⬇️ PDF",
                data=pdf_export.generate_personnel_pdf_export(admin_id, run_id, "teacher"),
                file_name=f"Teacherwise_Timetable_Run_{run_id}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key=f"teacher_pdf_{run_id}"
            )

        with e3:
            st.markdown("**🏛️ Room/Lab-wise**")
            st.download_button(
                "⬇️ Excel",
                data=excel_export.generate_excel_view_export(admin_id, run_id, "room"),
                file_name=f"Roomwise_Timetable_Run_{run_id}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key=f"room_excel_{run_id}"
            )
            st.download_button(
                "⬇️ PDF",
                data=pdf_export.generate_personnel_pdf_export(admin_id, run_id, "room"),
                file_name=f"Roomwise_Timetable_Run_{run_id}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key=f"room_pdf_{run_id}"
            )

        st.markdown("### 📦 Full Exports")
        c_exp1, c_exp2 = st.columns(2)
        with c_exp1:
            excel_bytes = excel_export.generate_excel_export(admin_id, run_id)
            st.download_button(
                label="⬇️ Download Full Excel Workbook",
                data=excel_bytes,
                file_name=f"Optimized_Timetable_Run_{run_id}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key=f"full_excel_{run_id}"
            )
        with c_exp2:
            pdf_bytes = pdf_export.generate_pdf_export(admin_id, run_id)
            st.download_button(
                label="⬇️ Download Full PDF",
                data=pdf_bytes,
                file_name=f"Optimized_Timetable_Run_{run_id}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key=f"full_pdf_{run_id}"
            )

# ============================================================
# 12. SETTINGS
# ============================================================
elif nav_option == "Settings":
    st.title("Administrator Settings")
    with st.form("settings_form"):
        col_s = database.get_admin_settings(admin_id)
        c_name = st.text_input("Institution Name", value=col_s['college_name'])
        a_year = st.text_input("Academic Year", value=col_s['academic_year'])
        dept = st.text_input("Department", value=col_s['department'])
        branch = st.text_input("Branch", value=col_s['branch'])
        t_limit = st.number_input("CP-SAT Solver Time Limit (seconds)", min_value=10, max_value=600, value=col_s['default_solver_time_limit'])

        if st.form_submit_button("Save Settings"):
            database.update_admin_settings(admin_id, c_name, a_year, dept, branch, t_limit)
            st.success("Settings updated successfully!")
            st.rerun()

# ============================================================
# 13. LOGOUT
# ============================================================
elif nav_option == "Logout":
    auth.logout_session()
    st.success("Logged out successfully.")
    st.rerun()
