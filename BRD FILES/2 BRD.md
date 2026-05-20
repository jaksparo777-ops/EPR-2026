# Foundry ERP — Business Requirements Document (BRD)

## 1. Project Overview
Foundry ERP is a comprehensive manufacturing and inventory management system designed for a metal foundry. It tracks the entire lifecycle of a product, from raw casting to final dispatch, including labor management, payroll, and stock visibility at every stage.

The system is built using the Django web framework and serves as a centralized hub for production data, master records, and financial ledgering for labor.

## 2. Business Objectives
- **End-to-End Traceability**: Track every piece of metal from the heat furnace (Casting) through various manufacturing stages.
- **Inventory Accuracy**: Maintain real-time stock levels across different warehouses (Casting, Machining, Polishing, Ready).
- **Labor Efficiency**: Manage both internal employees and external job workers, tracking their attendance, performance (production), and payments.
- **Financial Control**: Automate labor cost calculations, manage worker loans/advances, and maintain a clear audit trail of all transactions.
- **Streamlined Master Data**: Centralize management of items (BOMs), clients, and workers to ensure data consistency across the enterprise.

## 3. Key Modules & Features

### 3.1 Master Data Management
- **Item Master**: Central repository for all products. Includes weight tracking (casting vs. machining weight), process requirements (casting, machining, polishing, packing), and lot sizes.
- **BOM (Bill of Materials)**: Support for "Sets" or complex items composed of multiple sub-components (Kitting/Assembly).
- **Client Master**: Management of customer information and GST details.
- **Labor Management (Bifurcated)**:
    - **Internal Employees**: Professional HR profiles including Employee ID (auto-generated), designation, joining date, shift settings, and identity verification (Aadhar).
    - **Job Workers (External)**: Vendor profiles for external contractors with GST tracking and unique JW codes.
- **Warehouse Master**: Logical separation of stock locations (e.g., CASTING, MACHINING, READY).

### 3.2 Production Workflow
- **Casting Entry**: Record production from the furnace, linked to heat numbers and specific clients. Auto-calculates weights based on item master data.
- **Machining Module**: 
    - **Issue**: Handing over casted pieces to workers.
    - **Receipt**: Receiving machined pieces, tracking "Rejected Pieces" for quality control and inventory balancing.
- **Polishing Module**: Similar to machining, tracking the transition of pieces through the polishing stage.
- **Packaging**: Final stage tracking before items are moved to "Ready Stock".
- **Assembly (Kitting)**: Consuming component items to produce a "Parent Set" based on defined BOM ratios.

### 3.3 Inventory & Stock Tracking
- **StockTransaction Engine**: A robust backend that records every movement.
- **Dashboard**: Real-time visualization of stock levels at each stage (Pieces and Weight).
- **Stock Reports**: Detailed breakdown of inventory by item, client, or warehouse.

### 3.4 HR & Labor Finance
- **Attendance System**: Daily attendance tracking (Present, Absent, Half-Day) with overtime (OT) hour recording.
- **Payroll & Ledger**: 
    - Automatic salary/wage calculations based on different models (Daily, Fixed, Hourly).
    - Recording of payments (Salary, Advance, Job Work Payments).
    - **Loan Management**: Tracking loans issued to workers with automated EMI deductions.
- **Worker Performance**: Tracking production counts per worker to facilitate piece-rate or performance-based analysis.

### 3.5 Dispatch & Logistics
- **Order Fulfillment**: Tracking shipments to clients.
- **Carton Management**: Managing stock in both "Pieces" and "Cartons" for shipping convenience.

## 4. Technical Architecture
- **Backend**: Django (Python)
- **Database**: SQLite (Development/Current)
- **Frontend**: Vanilla HTML/CSS/JS with Django Templates. Enhanced with Tom Select for searchable dropdowns and modern UI aesthetics.
- **Integration**: RESTful API endpoints for dynamic frontend updates (Item composition, worker profiles, etc.).

## 5. System Workflows

### 5.1 The Production Cycle
1. **Master Data Setup**: Define Items, Clients, and Workers.
2. **Casting**: Input heat number and quantity. Stock enters "CASTING" warehouse.
3. **Processing**: Issue stock to a Worker/Job Worker. Stock moves to "WIP" (Work In Progress).
4. **Receipt**: Receive processed stock. Finished pieces move to the next stage; rejected pieces are deducted.
5. **Dispatch**: Final stock is moved to "READY" and eventually "DISPATCHED" to the client.

### 5.2 The Labor Cycle
1. **Attendance**: Marked daily for internal workers.
2. **Production**: Linked to workers during machining/polishing receipts.
3. **Payments**: Advances or loans recorded throughout the month.
4. **Settlement**: Monthly reports generated to calculate final dues after considering attendance, production, and loan deductions.

## 6. Future Scope
- **Advanced Analytics**: Trend analysis for heat efficiency and worker productivity.
- **Mobile Integration**: Barcode/QR scanning for stock movement.
- **Multi-User Permissions**: Role-based access control (Admin, Manager, Operator).
- **Cloud Migration**: Transitioning to a production-grade database (PostgreSQL) and cloud hosting.

---
*Document Version: 1.1*  
*Last Updated: 2026-05-16*
