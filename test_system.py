import os
import sys

# Ensure UTF-8 output encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def run_all_tests():
    print("==================================================")
    print("STARTING COMPREHENSIVE SYSTEM VERIFICATION TESTS")
    print("==================================================")

    # Test 1: Import Modules & Compilation
    print("\n[TEST 1] Testing Python Module Imports & Compilation...")
    try:
        import auth
        import database
        import validation
        import constraints
        import quality_score
        import timetable_engine
        import timetable_views
        import excel_export
        import pdf_export
        import demo_data
        print(" -> All Python modules imported successfully!")
    except Exception as e:
        print(f"FAILED [TEST 1]: Module import error: {e}")
        sys.exit(1)

    # Test 2: Database Initialization
    print("\n[TEST 2] Testing SQLite Database Initialization & Table Schemas...")
    try:
        # Clear test database file for clean test run
        if os.path.exists(database.DB_PATH):
            os.remove(database.DB_PATH)
        database.init_db()
        print(" -> Database schema initialized successfully.")
    except Exception as e:
        print(f"FAILED [TEST 2]: Database init error: {e}")
        sys.exit(1)

    # Test 3: Admin Registration & Password Security
    print("\n[TEST 3] Testing Admin Registration & Password Hashing...")
    try:
        # Register Admin A
        ok_a, msg_a = auth.register_admin("test_admin_a", "password123", "password123")
        assert ok_a, f"Admin A registration failed: {msg_a}"

        # Register Admin B
        ok_b, msg_b = auth.register_admin("test_admin_b", "securepass456", "securepass456")
        assert ok_b, f"Admin B registration failed: {msg_b}"

        # Retrieve Admins
        admin_a = database.get_admin_by_username("test_admin_a")
        admin_b = database.get_admin_by_username("test_admin_b")

        assert admin_a is not None and admin_b is not None
        assert admin_a['password_hash'] != "password123", "CRITICAL: Password stored as plain text!"
        assert auth.verify_password("password123", admin_a['password_hash'], admin_a['salt'])
        assert not auth.verify_password("wrongpass", admin_a['password_hash'], admin_a['salt'])

        print(f" -> Admin A ID: {admin_a['id']}, Admin B ID: {admin_b['id']}")
        print(" -> Secure password hashing & verification verified!")
    except Exception as e:
        print(f"FAILED [TEST 3]: Auth test error: {e}")
        sys.exit(1)

    # Test 4: Mandatory Multi-Admin Data Isolation Test
    print("\n[TEST 4] Testing Mandatory Multi-Admin Data Isolation...")
    try:
        admin_a_id = admin_a['id']
        admin_b_id = admin_b['id']

        # Admin A loads demo data
        ok_demo, demo_msg = demo_data.load_demo_data_for_admin(admin_a_id)
        assert ok_demo, f"Demo data loading failed for Admin A: {demo_msg}"

        # Admin B adds a distinct class B1
        class_b1_id = database.add_class(admin_b_id, "Class B1", "2026-27", "1st Year", "1st Semester", "CSE", "B", 50, "Prof. B")

        # Verify Admin A's view
        classes_a = database.get_classes(admin_a_id)
        class_names_a = [c['name'] for c in classes_a]
        assert "Class B1" not in class_names_a, "SECURITY VIOLATION: Admin A can see Admin B's class!"

        # Verify Admin B's view
        classes_b = database.get_classes(admin_b_id)
        class_names_b = [c['name'] for c in classes_b]
        assert "Class B1" in class_names_b, "Admin B cannot see Class B1!"
        assert "III B.Tech AIML-A" not in class_names_b, "SECURITY VIOLATION: Admin B can see Admin A's class!"

        print(" -> Data isolation verified! Admin A and Admin B data are completely segregated.")
    except Exception as e:
        print(f"FAILED [TEST 4]: Data isolation error: {e}")
        sys.exit(1)

    # Test 5: Input Validation Pre-Solve Check
    print("\n[TEST 5] Testing Pre-Solve Input Validation...")
    try:
        is_valid_a, errs_a = validation.validate_input_configuration(admin_a_id)
        assert is_valid_a, f"Input validation failed for Admin A: {errs_a}"

        is_valid_b, errs_b = validation.validate_input_configuration(admin_b_id)
        assert not is_valid_b, "Input validation should fail for Admin B (missing subjects/teachers), but passed!"
        print(f" -> Validation engine correctly identified missing config for Admin B: {errs_b[0]}")
    except Exception as e:
        print(f"FAILED [TEST 5]: Validation check error: {e}")
        sys.exit(1)

    # Test 6: Google OR-Tools CP-SAT Timetable Generation
    print("\n[TEST 6] Testing Google OR-Tools CP-SAT Timetable Optimization...")
    try:
        success, msg, res = timetable_engine.generate_timetable(admin_a_id)
        assert success, f"Timetable generation failed for Admin A: {msg}, payload: {res}"
        assert res['solver_status'] in ['OPTIMAL', 'FEASIBLE'], f"Unexpected solver status: {res['solver_status']}"
        assert res['is_valid_solution'] == True, f"Independent solution validation failed: {res.get('solution_validation_errors')}"
        assert res['quality_score'] > 0.0, "Quality score should be > 0"
        assert len(res['entries']) > 0, "No timetable entries generated!"

        print(f" -> Solver Status: {res['solver_status']}")
        print(f" -> Quality Score: {res['quality_score']}/100")
        print(f" -> Generated Entries Count: {len(res['entries'])}")
        print(f" -> Independent Validation Status: VALID [OK]")
    except Exception as e:
        print(f"FAILED [TEST 6]: CP-SAT engine error: {e}")
        sys.exit(1)

    # Test 7: Export Modules (Excel & PDF)
    print("\n[TEST 7] Testing Production Excel & PDF Export Generation...")
    try:
        run_id = res['run_id']

        # Excel Export
        excel_bytes = excel_export.generate_excel_export(admin_a_id, run_id)
        assert len(excel_bytes) > 1000, "Excel output file size too small!"
        print(f" -> Excel workbook generated successfully ({len(excel_bytes)} bytes).")

        # PDF Export
        pdf_bytes = pdf_export.generate_pdf_export(admin_a_id, run_id)
        assert len(pdf_bytes) > 1000, "PDF output file size too small!"
        print(f" -> PDF document generated successfully ({len(pdf_bytes)} bytes).")
    except Exception as e:
        print(f"FAILED [TEST 7]: Export generation error: {e}")
        sys.exit(1)

    print("\n==================================================")
    print("ALL VERIFICATION TESTS PASSED SUCCESSFULLY! [OK]")
    print("==================================================")

if __name__ == "__main__":
    run_all_tests()
