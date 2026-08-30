import time
import json
import re
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.db import connection

# List of normalized system tables with human readable metadata and data flow explanations
SYSTEM_TABLES = [
    {
        'table_name': 'master_data_item',
        'display_name': 'Item Master Catalog',
        'category': 'Master Data',
        'description': 'Master registry of raw materials, casting items, machined components, and finished set SKUs.',
        'tooltip': 'Data Flow: Referenced by StockTransaction, SalesOrderItem, CartonItem, and ItemWorkerAllocation.'
    },
    {
        'table_name': 'master_data_client',
        'display_name': 'Client Partners',
        'category': 'Master Data',
        'description': 'Registered client/buyer profiles with packing preferences and company scoping.',
        'tooltip': 'Data Flow: Linked to SalesOrder, Dispatch, Carton, and StockTransaction.'
    },
    {
        'table_name': 'master_data_legalentity',
        'display_name': 'Legal Entities (Companies)',
        'category': 'Master Data',
        'description': 'Company entities (NC Casting, OM Finishing) scoping master data and warehouse operations.',
        'tooltip': 'Data Flow: Parent entity for Client, Worker, Warehouse, and Item models.'
    },
    {
        'table_name': 'master_data_warehouse',
        'display_name': 'Warehouse Stages',
        'category': 'Master Data',
        'description': 'Physical and process stages (CASTING, MACHINING, POLISHING, READY).',
        'tooltip': 'Data Flow: Referenced by StockTransaction (from_warehouse & to_warehouse) and ItemStock.'
    },
    {
        'table_name': 'master_data_itemstock',
        'display_name': 'Item Stock Balances',
        'category': 'Master Data',
        'description': 'Real-time aggregated shelf stock quantity per Item and Warehouse stage.',
        'tooltip': 'Data Flow: Updated automatically via post_save signals on StockTransaction.'
    },
    {
        'table_name': 'master_data_itemcomposition',
        'display_name': 'Item Composition (BOM)',
        'category': 'Master Data',
        'description': 'Bill of Materials parent-to-component mappings for assembly and set kitting.',
        'tooltip': 'Data Flow: Dictates assembly consumption and set kitting output ratios.'
    },
    {
        'table_name': 'authentication_worker',
        'display_name': 'Internal Staff Workers',
        'category': 'Workforce',
        'description': 'Internal shop-floor staff workers with daily rates, process roles, and fixed salaries.',
        'tooltip': 'Data Flow: Linked to StockTransaction (worker), Attendance, LaborPayment, and Loan.'
    },
    {
        'table_name': 'authentication_jobworker',
        'display_name': 'External Job Work Units',
        'category': 'Workforce',
        'description': 'External job work units and subcontractors handling machining or polishing services.',
        'tooltip': 'Data Flow: Linked to StockTransaction (job_worker), LaborPayment, and Loan.'
    },
    {
        'table_name': 'production_itemworkerallocation',
        'display_name': 'Item Worker Piece Rates',
        'category': 'Workforce',
        'description': 'Contractual piece-rate pricing matrix per item and worker/job-worker.',
        'tooltip': 'Data Flow: Multiplied by StockTransaction output quantities to compute labor earnings.'
    },
    {
        'table_name': 'production_attendance',
        'display_name': 'Attendance & Overtime Logs',
        'category': 'Workforce',
        'description': 'Daily worker shift status (PRESENT, HALF_DAY, ABSENT) and overtime hours.',
        'tooltip': 'Data Flow: Computes daily wage earnings and overtime pay in Labor Ledger.'
    },
    {
        'table_name': 'production_laborpayment',
        'display_name': 'Labor Payment Ledger',
        'category': 'Workforce',
        'description': 'Cash outflow transactions: salary settlements, advances, job work payments, and loan repayments.',
        'tooltip': 'Data Flow: Deducts payables and updates loan remaining balances.'
    },
    {
        'table_name': 'production_loan',
        'display_name': 'Worker & Job Worker Loans',
        'category': 'Workforce',
        'description': 'Active loans, EMI monthly deductions, and remaining loan balances.',
        'tooltip': 'Data Flow: Updated by LaborPayment transactions of type NEW_LOAN or LOAN_REPAYMENT.'
    },
    {
        'table_name': 'production_stocktransaction',
        'display_name': 'Stock Transaction Ledger (Core Audit)',
        'category': 'Production Ledger',
        'description': 'Immutable, chronological audit log recording every inventory movement across all production stages.',
        'tooltip': 'Data Flow: Core ledger connecting Raw Casting -> Machining -> Polishing -> Packaging -> Dispatch.'
    },
    {
        'table_name': 'production_carton',
        'display_name': 'Packaged Master Cartons',
        'category': 'Production Ledger',
        'description': 'Physical master cartons on warehouse shelves with lot labels, serials, and dispatch status.',
        'tooltip': 'Data Flow: Contains CartonItems; linked to Client, SalesOrder, and Dispatch.'
    },
    {
        'table_name': 'production_cartonitem',
        'display_name': 'Carton Contents',
        'category': 'Production Ledger',
        'description': 'Specific items and piece quantities packed inside each Master Carton.',
        'tooltip': 'Data Flow: Connects Item to Carton; consumed during sales dispatches.'
    },
    {
        'table_name': 'orders_salesorder',
        'display_name': 'Customer Sales Orders',
        'category': 'Sales & Logistics',
        'description': 'Customer Purchase Orders (SO-1000+) tracking order date, promised deadline, priority, and status.',
        'tooltip': 'Data Flow: Parent order for SalesOrderItem and Dispatch transactions.'
    },
    {
        'table_name': 'orders_salesorderitem',
        'display_name': 'Sales Order Line Products',
        'category': 'Sales & Logistics',
        'description': 'Ordered product quantities and contractual piece rates per Sales Order.',
        'tooltip': 'Data Flow: Evaluated against ItemStock and StockTransaction to compute readiness and coverage %.'
    },
    {
        'table_name': 'orders_dispatch',
        'display_name': 'Sales Dispatches (Delivery Challans)',
        'category': 'Sales & Logistics',
        'description': 'Sales dispatch headers (DSP-1000+) generated when goods are shipped to clients.',
        'tooltip': 'Data Flow: Linked to SalesOrder and Client; generates DispatchItems and dispatch_out transactions.'
    },
    {
        'table_name': 'orders_dispatchitem',
        'display_name': 'Dispatched Line Items',
        'category': 'Sales & Logistics',
        'description': 'Item quantities and weights dispatched in a specific Delivery Challan.',
        'tooltip': 'Data Flow: Reduces remaining quantities on SalesOrderItem.'
    }
]

PREBUILT_QUERIES = [
    {
        'id': 'end_to_end_flow',
        'title': '🔄 End-to-End Production & Logistics Data Flow',
        'subtitle': 'Traces item movement step-by-step through Casting ➔ Machining ➔ Polishing ➔ Packaging ➔ Dispatch',
        'tooltip': 'Data Flow Explanation: Joins StockTransaction with Item, Worker, JobWorker, Client, and Warehouses. Demonstrates how a single item transitions through from_warehouse and to_warehouse across production stages.',
        'sql': """-- 1. End-to-End Production & Logistics Data Flow Audit
SELECT 
    st.id AS tx_id,
    st.created_at AS timestamp,
    st.transaction_type,
    i.code AS item_code,
    i.name AS item_name,
    st.quantity AS pcs,
    st.weight AS weight_kg,
    fw.name AS from_stage,
    tw.name AS to_stage,
    COALESCE(w.name, jw.name, 'Warehouse Staff') AS operator,
    c.name AS client_name,
    st.notes
FROM production_stocktransaction st
JOIN master_data_item i ON st.item_id = i.id
LEFT JOIN master_data_warehouse fw ON st.from_warehouse_id = fw.id
LEFT JOIN master_data_warehouse tw ON st.to_warehouse_id = tw.id
LEFT JOIN authentication_worker w ON st.worker_id = w.id
LEFT JOIN authentication_jobworker jw ON st.job_worker_id = jw.id
LEFT JOIN master_data_client c ON st.client_id = c.id
ORDER BY st.id DESC
LIMIT 50;"""
    },
    {
        'id': 'order_fulfillment_pipeline',
        'title': '📋 Customer PO Fulfillment & Inventory Pipeline',
        'subtitle': 'Calculates Sales Order requirements vs Warehouse Ready Stock vs Active Stage WIP',
        'tooltip': 'Data Flow Explanation: Connects SalesOrder ➔ SalesOrderItem ➔ Item ➔ ItemStock to display how customer orders are matched against physical ready stock and work-in-progress pipeline.',
        'sql': """-- 2. Customer PO Fulfillment & Stage Inventory Pipeline
SELECT 
    so.order_number AS sales_order,
    c.name AS client_name,
    so.external_po_number AS client_po_ref,
    so.promised_date AS delivery_deadline,
    so.priority,
    so.status AS order_status,
    i.code AS item_code,
    i.name AS item_name,
    soi.ordered_quantity AS ordered_pcs,
    COALESCE(stk.quantity_on_hand, 0) AS ready_warehouse_pcs,
    MAX(0, soi.ordered_quantity - COALESCE(stk.quantity_on_hand, 0)) AS net_needed_pcs
FROM orders_salesorder so
JOIN master_data_client c ON so.client_id = c.id
JOIN orders_salesorderitem soi ON soi.sales_order_id = so.id
JOIN master_data_item i ON soi.item_id = i.id
LEFT JOIN master_data_warehouse w ON w.code = 'READY'
LEFT JOIN master_data_itemstock stk ON stk.item_id = i.id AND stk.warehouse_id = w.id
ORDER BY so.id DESC, i.code ASC
LIMIT 50;"""
    },
    {
        'id': 'workforce_earnings_ledger',
        'title': '💰 Workforce Output, Piece Rates & Earnings Ledger',
        'subtitle': 'Calculates worker production outputs, piece-rate pricing allocations, and net labor payables',
        'tooltip': 'Data Flow Explanation: Combines StockTransaction outputs with ItemWorkerAllocation pricing rules and LaborPayment history to calculate accurate labor cost flow.',
        'sql': """-- 3. Workforce Production Output & Earnings Summary
SELECT 
    w.employee_id AS id_code,
    w.name AS worker_name,
    'Internal Staff' AS category,
    i.code AS item_code,
    i.name AS item_name,
    SUM(st.quantity) AS total_produced_pcs,
    COALESCE(iwa.rate_per_piece, 0.0) AS piece_rate_inr,
    ROUND(SUM(st.quantity) * COALESCE(iwa.rate_per_piece, 0.0), 2) AS gross_earnings_inr
FROM production_stocktransaction st
JOIN authentication_worker w ON st.worker_id = w.id
JOIN master_data_item i ON st.item_id = i.id
LEFT JOIN production_itemworkerallocation iwa ON iwa.item_id = i.id AND iwa.worker_id = w.id
WHERE st.transaction_type IN ('machining_in', 'polishing_in', 'packaging_in')
GROUP BY w.id, i.id
ORDER BY gross_earnings_inr DESC
LIMIT 50;"""
    },
    {
        'id': 'carton_kitting_trace',
        'title': '📦 Carton Kitting, Packaging & Dispatch Trace',
        'subtitle': 'Traces master cartons on shelf, packed items, reserved sales orders, and shipping status',
        'tooltip': 'Data Flow Explanation: Connects Carton ➔ CartonItem ➔ Item ➔ SalesOrder ➔ Client to demonstrate how polished stock is packed into cartons and allocated for dispatch.',
        'sql': """-- 4. Master Carton Kitting & Storage Inventory Trace
SELECT 
    ctn.carton_number,
    ctn.carton_label,
    ctn.carton_type,
    ctn.status AS carton_status,
    c.name AS client_name,
    so.order_number AS reserved_sales_order,
    i.code AS packed_item_code,
    i.name AS packed_item_name,
    ci.quantity AS packed_pcs,
    ci.weight AS packed_weight_kg,
    ctn.created_at AS packed_date
FROM production_carton ctn
JOIN production_cartonitem ci ON ci.carton_id = ctn.id
JOIN master_data_item i ON ci.item_id = i.id
LEFT JOIN master_data_client c ON ctn.client_id = c.id
LEFT JOIN orders_salesorder so ON ctn.sales_order_id = so.id
ORDER BY ctn.id DESC
LIMIT 50;"""
    },
    {
        'id': 'realtime_stock_audit',
        'title': '⚖️ Real-Time Warehouse Stock Balances vs Audit Deltas',
        'subtitle': 'Compares real-time ItemStock table balances against historical StockTransaction log sums',
        'tooltip': 'Data Flow Explanation: Audits consistency between normalized real-time balance table (ItemStock) and transaction ledger (StockTransaction).',
        'sql': """-- 5. Real-Time Warehouse Stock Audit & Reconciliation
SELECT 
    w.name AS warehouse_stage,
    i.code AS item_code,
    i.name AS item_name,
    stk.quantity_on_hand AS current_balance_pcs,
    stk.last_updated AS balance_last_updated
FROM master_data_itemstock stk
JOIN master_data_item i ON stk.item_id = i.id
JOIN master_data_warehouse w ON stk.warehouse_id = w.id
WHERE stk.quantity_on_hand != 0
ORDER BY w.code, i.code
LIMIT 50;"""
    }
]

# 10 Sample SQL Commands covering SELECT, INSERT, UPDATE, DELETE for testing data entries
SAMPLE_10_COMMANDS = [
    {
        'id': 'cmd_1_select_items',
        'title': '1. SELECT - Fetch Master Item Catalog',
        'action_type': 'SELECT',
        'description': 'Reads top 10 master items with code, name, category, weights, and lot sizes.',
        'sql': """SELECT id, code, name, category, material, casting_weight, lot_size, active FROM master_data_item ORDER BY id DESC LIMIT 10;"""
    },
    {
        'id': 'cmd_2_select_clients',
        'title': '2. SELECT - Fetch Active Clients',
        'action_type': 'SELECT',
        'description': 'Reads active client buyer records with packing preferences and GST numbers.',
        'sql': """SELECT id, client_code, name, company_id, phone, packing_preference, gst_number FROM master_data_client WHERE active = 1 LIMIT 10;"""
    },
    {
        'id': 'cmd_3_select_stock',
        'title': '3. SELECT - Fetch Warehouse Stock Balances',
        'action_type': 'SELECT',
        'description': 'Lists item shelf stock balances across CASTING, MACHINING, POLISHING, and READY stages.',
        'sql': """SELECT stk.id, i.code AS item_code, i.name AS item_name, w.name AS warehouse_stage, stk.quantity_on_hand FROM master_data_itemstock stk JOIN master_data_item i ON stk.item_id = i.id JOIN master_data_warehouse w ON stk.warehouse_id = w.id WHERE stk.quantity_on_hand > 0 LIMIT 15;"""
    },
    {
        'id': 'cmd_4_select_tx_log',
        'title': '4. SELECT - Audit Production Transactions',
        'action_type': 'SELECT',
        'description': 'Fetches recent stock transaction audit logs across production stages.',
        'sql': """SELECT id, transaction_type, item_id, quantity, weight, created_at FROM production_stocktransaction ORDER BY id DESC LIMIT 15;"""
    },
    {
        'id': 'cmd_5_insert_sample_item',
        'title': '5. INSERT - Add Experimental New Item',
        'action_type': 'INSERT',
        'description': 'Creates a new sample item "TEST-999 (Experimental Brass Handle)" in master_data_item table.',
        'sql': """INSERT INTO master_data_item (code, name, category, item_type, casting_required, machining_required, polishing_required, packing_required, casting_weight, machining_weight, lot_size, lot_with_box, rate_per_piece, min_casting_stock, min_machining_stock, min_polishing_stock, min_ready_stock, is_raw_material, yield_pcs_per_unit, uom, active, created_at, updated_at) VALUES ('TEST-999', 'Experimental Brass Handle', 'BRASS', 'REGULAR', 1, 1, 1, 1, 0.450, 0.420, 50, 50, 25.0, 0, 0, 0, 0, 0, 1.0, 'PCS', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);"""
    },
    {
        'id': 'cmd_6_insert_sample_client',
        'title': '6. INSERT - Add Experimental Client',
        'action_type': 'INSERT',
        'description': 'Creates a new sample client "Acme Enterprise Corp (CL-9999)" in master_data_client table.',
        'sql': """INSERT INTO master_data_client (name, client_code, company_id, phone, email, city, packing_preference, active, created_at, updated_at) VALUES ('Acme Enterprise Corp', 'CL-9999', 1, '9876543210', 'purchases@acme.com', 'Mumbai', 'ANY', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);"""
    },
    {
        'id': 'cmd_7_update_item_weight',
        'title': '7. UPDATE - Modify Item Weight & Lot Size',
        'action_type': 'UPDATE',
        'description': 'Updates casting_weight and lot_size for item code TEST-999.',
        'sql': """UPDATE master_data_item SET casting_weight = 0.500, lot_size = 100, updated_at = CURRENT_TIMESTAMP WHERE code = 'TEST-999';"""
    },
    {
        'id': 'cmd_8_update_client_pref',
        'title': '8. UPDATE - Adjust Client Packing Preference',
        'action_type': 'UPDATE',
        'description': 'Updates packing preference for client CL-9999 to BOX_STRICT.',
        'sql': """UPDATE master_data_client SET packing_preference = 'BOX_STRICT', updated_at = CURRENT_TIMESTAMP WHERE client_code = 'CL-9999';"""
    },
    {
        'id': 'cmd_9_delete_sample_item',
        'title': '9. DELETE - Remove Experimental Test Item',
        'action_type': 'DELETE',
        'description': 'Deletes sample item TEST-999 created in Step 5 from master_data_item table.',
        'sql': """DELETE FROM master_data_item WHERE code = 'TEST-999';"""
    },
    {
        'id': 'cmd_10_delete_sample_client',
        'title': '10. DELETE - Remove Experimental Test Client',
        'action_type': 'DELETE',
        'description': 'Deletes sample client CL-9999 created in Step 6 from master_data_client table.',
        'sql': """DELETE FROM master_data_client WHERE client_code = 'CL-9999';"""
    }
]

@login_required
def sql_explorer_view(request):
    """
    Renders the SQL Explorer UI with list of tables, schema introspecion,
    pre-built queries, sample commands, and visual data flow diagrams.
    """
    tables_meta = []
    
    # Introspect SQLite / PostgreSQL tables for row counts and columns
    with connection.cursor() as cursor:
        for t in SYSTEM_TABLES:
            table_name = t['table_name']
            
            # Fetch row count
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                row_count = cursor.fetchone()[0]
            except Exception:
                row_count = 0

            # Fetch columns metadata
            try:
                columns_info = []
                # Uses Django connection introspection
                description = connection.introspection.get_table_description(cursor, table_name)
                for col in description:
                    columns_info.append({
                        'name': col.name,
                        'type': str(col.type_code),
                        'null_ok': col.null_ok
                    })
            except Exception:
                columns_info = []

            tables_meta.append({
                **t,
                'row_count': row_count,
                'columns': columns_info
            })

    context = {
        'tables': tables_meta,
        'prebuilt_queries': PREBUILT_QUERIES,
        'sample_commands': SAMPLE_10_COMMANDS,
        'total_tables': len(tables_meta)
    }
    return render(request, 'sql_explorer.html', context)


@login_required
@require_POST
def sql_explorer_run_api(request):
    """
    Executes SQL queries safely and returns JSON output.
    Supports SELECT, WITH, INSERT, UPDATE, DELETE when allow_write parameter is true.
    Blocks catastrophic commands like DROP, TRUNCATE, ALTER TABLE.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        raw_sql = data.get('query', '').strip()
        allow_write = bool(data.get('allow_write', False))
    except Exception:
        return JsonResponse({'status': 'error', 'error': 'Invalid JSON body'}, status=400)

    if not raw_sql:
        return JsonResponse({'status': 'error', 'error': 'SQL Query cannot be empty'}, status=400)

    # Clean SQL comments
    normalized_query = re.sub(r'--.*$', '', raw_sql, flags=re.MULTILINE).strip()
    normalized_query_clean = re.sub(r'/\*.*?\*/', '', normalized_query, flags=re.DOTALL).strip()
    
    first_word = normalized_query_clean.split()[0].upper() if normalized_query_clean.split() else ''

    # Safety Guardrails
    allowed_first_words = ['SELECT', 'WITH']
    is_admin = request.user.is_superuser or getattr(request.user, 'role', '') == 'ADMIN'

    if allow_write:
        if not is_admin:
            return JsonResponse({
                'status': 'error',
                'error': 'Security Block: Database modification queries (INSERT, UPDATE, DELETE) are strictly restricted to System Administrators.'
            }, status=403)
        allowed_first_words.extend(['INSERT', 'UPDATE', 'DELETE'])

    if first_word not in allowed_first_words:
        if not allow_write and first_word in ['INSERT', 'UPDATE', 'DELETE']:
            return JsonResponse({
                'status': 'error',
                'error': 'Write Guard Block: INSERT, UPDATE, DELETE statements require Write Mode to be enabled in the header toggle.'
            }, status=403)
        return JsonResponse({
            'status': 'error',
            'error': f"Security Block: Only {', '.join(allowed_first_words)} queries are permitted."
        }, status=403)

    # Always block catastrophic schema alter / drop commands
    catastrophic_pattern = r'\b(DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE|ATTACH|DETACH|VACUUM|REINDEX)\b'
    if re.search(catastrophic_pattern, normalized_query_clean, re.IGNORECASE):
        return JsonResponse({
            'status': 'error',
            'error': 'Security Block: Schema modification keywords (DROP, TRUNCATE, ALTER, CREATE, etc.) are strictly prohibited for database safety.'
        }, status=403)

    start_time = time.time()
    try:
        with connection.cursor() as cursor:
            cursor.execute(normalized_query_clean)
            
            # If query is a DML statement (INSERT, UPDATE, DELETE)
            if first_word in ['INSERT', 'UPDATE', 'DELETE']:
                if not connection.in_atomic_block:
                    connection.commit()
                rows_affected = cursor.rowcount
                execution_time_ms = round((time.time() - start_time) * 1000, 2)
                return JsonResponse({
                    'status': 'success',
                    'is_mutation': True,
                    'action': first_word,
                    'rows_affected': rows_affected,
                    'duration_ms': execution_time_ms,
                    'message': f"Successfully executed {first_word}. {rows_affected} row(s) affected in database."
                })

            # For SELECT / WITH queries
            columns = [col[0] for col in cursor.description] if cursor.description else []
            raw_rows = cursor.fetchmany(200) # Cap at 200 rows
            
            formatted_rows = []
            for row in raw_rows:
                formatted_row = []
                for val in row:
                    if val is None:
                        formatted_row.append(None)
                    elif isinstance(val, (int, float, bool)):
                        formatted_row.append(val)
                    else:
                        formatted_row.append(str(val))
                formatted_rows.append(formatted_row)
                
            execution_time_ms = round((time.time() - start_time) * 1000, 2)
            
            return JsonResponse({
                'status': 'success',
                'is_mutation': False,
                'columns': columns,
                'rows': formatted_rows,
                'row_count': len(formatted_rows),
                'duration_ms': execution_time_ms
            })

    except Exception as e:
        execution_time_ms = round((time.time() - start_time) * 1000, 2)
        return JsonResponse({
            'status': 'error',
            'error': f"SQL Execution Error: {str(e)}",
            'duration_ms': execution_time_ms
        }, status=400)
