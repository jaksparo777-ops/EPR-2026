# Business Requirements Document (BRD)
## Foundry ERP System Overhaul, Lot-Preservation Packaging, & Dispatch Lifecycle

**Document Reference:** BRD-ERP-2026-V2.0  
**Date:** May 19, 2026  
**Project Workspace:** Foundry ERP (`jaksparo777-ops/EPR-2026`)  
**Status:** Approved & Implemented  

---

## 1. Executive Summary
The Foundry ERP is a comprehensive, enterprise-ready resource planning system designed to manage and optimize production, inventory, labor, packaging, and client dispatch cycles for foundry operations. This document highlights the complete business requirements, functional scopes, and technical design directives implemented across all modules—from raw casting heats to database-level polishing lot splits, multi-item carton assembly, ready stock warehouse logs, and dual-tab dispatch workflows.

---

## 2. Business Objectives
* **Operational Clarity:** Establish strict structural division between internal employees (salaried/shift-based) and external job workers (piece-rate vendors).
* **Lot Size & Stock Integrity:** Preserve standard lot sizes (e.g. 35-pc regular lots and 36-pc box lots) from the moment they are issued to workers, through receipt returns, into the packaging queue, and during carton dispatch to prevent stock errors.
* **Warehouse & Ready Stock Visibility:** Maintain real-time tracking of ready cartons sitting on warehouse shelves, nested contents breakdown, and piece-to-carton packing ratios.
* **Labor Auto-Allocation & Live Auditing:** Capture labor costs, piece-rate allocations, and display warning badges for any transaction lacking a defined process rate.
* **Enhanced Data Entry & Dispatch Efficiency:** Redesign the daily entry grids to support responsive searchable controls (Tom Select) and feature a premium dual-tab dispatch drawer (Ready Cartons vs Manual Pieces Override).
* **Frictionless Daily HR Entry**: Implement an ultra-fast, fully interactive grid for daily attendance logging that supports zero-click keyboard hotkeys and multi-click mouse triggers with live overtime integration.
* **Granular Quality & Defect Management**: Symmetrically handle item rejections during polishing mark-ins (via split-click) and component-level SET rejections (replacing exactly the defective component from the loose buffer stock while keeping the packed carton full).

---

## 3. Detailed Business Requirements & Functional Scope

### A. Worker & Labor Management
| Requirement ID | Requirement Description | Implementation Details |
| :--- | :--- | :--- |
| **REQ-HR-001** | Strict bifurcated directory for Internal Employees and Job Workers. | Separate database schemas and management pages for internal staff (`Worker` model) and external vendors (`JobWorker` model). |
| **REQ-HR-002** | Automated Worker Identification Codes. | Auto-generate professional standard identification codes upon profile creation if left blank: `EMP-XXXX` for internal staff and `JW-XXXX` for job workers. |
| **REQ-HR-003** | Dynamic Labor Rate Allocation. | Enable allocating specific processes (Casting, Machining, Polishing, Packaging) and rate-per-piece costs to items for individual job workers. |
| **REQ-HR-004** | "No Rate Set" Live Audits. | Automatically trigger warning flags (`₹0 (No Rate Set)`) in production logs and statements if an inward transaction has no matching worker rate. |
| **REQ-HR-005** | **Lightning-Fast Inline Attendance Sheet Grid**. | Daily attendance sheet cells register status updates via zero-click keyboard hotkeys (`p`->Present, `a`->Absent, `h`->Half-Day, `c`->Clear) when hovered, or via multi-click mouse events (single->Present, double->Absent, triple->Half-day) with a green/red tactile pulse animation and auto-saving inline overtime input boxes. |

### B. Inventory & Bill of Materials (BOM) Master Data
| Requirement ID | Requirement Description | Implementation Details |
| :--- | :--- | :--- |
| **REQ-INV-001** | Multidimensional Item Classification. | Support high-detail bifurcation using a three-tier taxonomy: **Category**, **Sub-Category**, and **Variant** fields. |
| **REQ-INV-002** | Automated BOM Component Merging. | When a Set/BOM is created, automatically inherit, merge, and map component-level details (Material, Category, Client) to the parent item. |
| **REQ-INV-003** | Auto-allocation of BOM Labor Rates. | Sum and map all individual component worker rate allocations directly to the parent Set profile to ensure total cost accuracy. |
| **REQ-INV-004** | Contextual Item Specification Forms. | When a single item (Regular/Single type) is selected, streamline the drawer view to display only a field asking for quantity (PCS), hiding complex sub-component settings. |
| **REQ-INV-005** | Category Sidebar Filters. | Group and dynamically filter all items in the ERP Item Master dashboard by their active categories, updating category item counts in real-time. |
| **REQ-INV-006** | **Polished Loose Buffer Stock Tab**. | Dedicated global navigation tab showing all loose bag buffer pieces available across the factory, filtered to only show items with dynamic buffer levels > 0. |
| **REQ-INV-007** | **Subcategory Panel Bifurcation**. | Group and arrange loose polished stock inside dynamic folder panels (e.g. `📁 DASTA`) with client-side dynamic search card filtering to instantly hide empty categories. |

### C. Daily Production & WIP Balancing (Casting & Machining)
| Requirement ID | Requirement Description | Implementation Details |
| :--- | :--- | :--- |
| **REQ-PROD-001** | Searchable Production Input Toggles. | Integrate Tom Select on all machining and polishing transaction screens for swift searchable worker/item drop-downs. |
| **REQ-PROD-002** | Precise Reject Tracking. | Support direct editing of daily entries and capture "Rejected Pieces" to track defects and scrap directly. |
| **REQ-PROD-003** | Live WIP Balancing. | Auto-calculate Work-In-Progress balances (Issued vs. Received vs. Rejected) to maintain absolute stock integrity across production checkpoints. |

### D. Advanced Polishing & Lot Preservation
| Requirement ID | Requirement Description | Implementation Details |
| :--- | :--- | :--- |
| **REQ-PROD-004** | Worker-Grouped Assigned WIP. | Group outstanding WIP entries directly under worker headers (`👤`) with pending item details, pending quantities, and an instant **Mark IN** button. |
| **REQ-PROD-005** | **1-Click Lot-Preserving Group Mark IN**. | Clicking **Mark IN** instantly receives all outstanding issue entries for that worker and item. Symmetrically queries active issues chronologically, matching their exact original lot sizes (such as regular lots of **35** and box lots of **36**) and weights to prevent database lot degradation. |
| **REQ-PROD-006** | **Database-Level Polishing Lot Splitting**. | Custom manual receipt form submissions (lots + manual leftovers) are physically split into separate standard lot and manual remainder database ledger transactions with proportional weight distribution and component auto-consumptions. |

### E. Packaging & Ready Stock Warehouse
| Requirement ID | Requirement Description | Implementation Details |
| :--- | :--- | :--- |
| **REQ-PKG-001** | Standard Lot-Size Queue & **PACK NOW**. | Packaging Queue displays entries based natively on original database return receipts. Clicking **PACK NOW** instantly packs the entire remaining quantity of that specific entry into a standard carton of its correct lot size. |
| **REQ-PKG-002** | **Mixed Carton Bucket Drawer**. | Slide-up drawer allowing multi-selecting outstanding queue rows to combine items (sets + single items + extra pieces) into 1 mixed carton with process checklists (cleaning, labeling, packing). |
| **REQ-PKG-003** | **Physical Carton Warehouse Shelf**. | Live warehouse shelf displaying ready cartons, nested carton item breakdowns, and piece-to-carton packing ratios. |
| **REQ-PKG-004** | **Packaging Queue "📂 Spare" (Buffer Sparing)**. | Interactive spares action that lets operators declare pending lot pieces as loose buffer spares. Creates special `packaging_in` transactions with `[DEDICATED BUFFER]` notes which exclude them from standard packaging deductions, keeping physical stock balanced. |
| **REQ-PKG-005** | **Split-Click Polishing Mark-In Rejections**. | WIP and Recent Activity mark-in buttons support mouse event splitting: single-click logs instant mark-in, double-click pops up a glowing glassmorphic rejections entry modal to record scrap and reduce outstanding WIP queues. |
| **REQ-PKG-006** | **SET Component Quality Inspection & Rejections**. | Selecting a parent SET item dynamically expands the Quality Inspection drawer, showing independent component rejection input fields with live buffer numbers. Replacing defective pieces from loose stock creates a targeted component deduction (`[DEDICATED BUFFER CONSUMPTION]`), keeping the parent carton 100% full. |

### F. Client Dispatch & Outbound Ledger Sync
| Requirement ID | Requirement Description | Implementation Details |
| :--- | :--- | :--- |
| **REQ-DSP-001** | **Premium Dual-Tab Drawer**. | **Tab 1 (Select Ready Cartons)** renders a checkbox list of ready cartons with a live piece and weight summation bar. **Tab 2 (Manual Pieces Override)** supports entering manual loose quantities with auto-weight estimates. |
| **REQ-DSP-002** | **Client Allocation & Outbound Sync**. | Dispatches automatically update carton statuses to `DISPATCHED`, log client assignments, and record dual-written outbound stock transactions. |

---

## 4. Technical Architecture & Design Directives
* **Backend Architecture:** Built on Django, utilizing strong relational schema rules (`ForeignKey`, `OneToOneField`) and services (`merge_bom_component_details`, `sync_bom_worker_allocations`) to ensure cascading changes and real-time data synchronizations.
* **FIFO Credit Matching:** Relies on a running credit balance algorithm for lot-preserving group mark-ins, ensuring perfect ledger alignment regardless of historical data notes.
* **Frontend Design System:** Glassmorphism UI styled with sleek, customized Tailwind-complementary HSL palettes, vivid alerts, micro-animations, and slide-out drawers.

---

## 5. Verification & Quality Standards
* **Automated Test Coverage:** Complete Django test modules verifying inventory, BOM creation, and labor ledger rate mappings.
* **Integration verification suite:** Automated script (`test_lot_splitting.py`) simulating chronological issues (35, 36, 35 pcs), group mark-in lot preservation, queue displays, and standard carton packaging.
