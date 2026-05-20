# Business Requirements Document (BRD)
## Foundry ERP System Overhaul & Labor Allocation Module

**Document Reference:** BRD-ERP-2026-V1.0  
**Date:** May 18, 2026  
**Project Workspace:** Foundry ERP (`jaksparo777-ops/EPR-2026`)  
**Status:** Approved & Implemented  

---

## 1. Executive Summary
The Foundry ERP is a comprehensive enterprise resource planning system designed to manage and optimize production, inventory, labor, and client cycles for foundry operations. This document highlights the business requirements and technical design directives implemented to streamline the master data workflow, labor auto-allocation, production tracking, and bifurcated worker directory management.

---

## 2. Business Objectives
- **Operational Clarity:** Establish strict structural division between internal employees (salaried/shift-based) and external job workers (rate-per-piece piece-rate vendors).
- **Data Integrity & Traceability:** Automate the mapping of all metadata fields (Category, Sub-Category, Variant, Material, Client) from individual components to parent Sets during Bill of Materials (BOM) compilation to eliminate duplicate entry.
- **WIP & Cost Visibility:** Capture live labor costs and piece-rate allocations directly within the inventory and assembly catalog, displaying warning badges for any record lacking a defined process rate.
- **Enhanced Data Entry Efficiency:** Redesign the machining, polishing, and master data layouts to feature responsive, searchable controls (Tom Select) and color-coded process directives that accelerate daily production logging.

---

## 3. Detailed Business Requirements & Functional Scope

### A. Worker & Labor Management
| Requirement ID | Requirement Description | Implementation Details |
| :--- | :--- | :--- |
| **REQ-HR-001** | Strict bifurcated directory for Internal Employees and Job Workers. | Separate database schemas and management pages for internal staff (`Worker` model) and external vendors (`JobWorker` model). |
| **REQ-HR-002** | Automated Worker Identification Codes. | Auto-generate professional standard identification codes upon profile creation if left blank: `EMP-XXXX` for internal staff and `JW-XXXX` for job workers. |
| **REQ-HR-003** | Dynamic Labor Rate Allocation. | Enable allocating specific processes (Casting, Machining, Polishing, Packaging) and rate-per-piece costs to items for individual job workers. |
| **REQ-HR-004** | "No Rate Set" Live Audits. | Automatically trigger warning flags (`₹0 (No Rate Set)`) in production logs and statements if an inward transaction has no matching worker rate. |

### B. Inventory & Bill of Materials (BOM) Master Data
| Requirement ID | Requirement Description | Implementation Details |
| :--- | :--- | :--- |
| **REQ-INV-001** | Multidimensional Item Classification. | Support high-detail bifurcation using a three-tier taxonomy: **Category**, **Sub-Category**, and **Variant** fields. |
| **REQ-INV-002** | Automated BOM Component Merging. | When a Set/BOM is created, automatically inherit, merge, and map component-level details (Material, Category, Client) to the parent item. |
| **REQ-INV-003** | Auto-allocation of BOM Labor Rates. | Sum and map all individual component worker rate allocations directly to the parent Set profile to ensure total cost accuracy. |
| **REQ-INV-004** | Contextual Item Specification Forms. | When a single item (Regular/Single type) is selected, streamline the drawer view to display only a single field asking for quantity (PCS), hiding complex sub-component settings. |
| **REQ-INV-005** | Category Sidebar Filters. | Group and dynamically filter all items in the ERP Item Master dashboard by their active categories, updating category item counts in real-time. |

### C. Daily Production & WIP Balancing
| Requirement ID | Requirement Description | Implementation Details |
| :--- | :--- | :--- |
| **REQ-PROD-001** | Searchable Production Input Toggles. | Integrate Tom Select on all machining and polishing transaction screens for swift searchable worker/item drop-downs. |
| **REQ-PROD-002** | Precise Reject Tracking. | Support direct editing of daily entries and capture "Rejected Pieces" to track defects and scrap directly. |
| **REQ-PROD-003** | Live WIP Balancing. | Auto-calculate Work-In-Progress balances (Issued vs. Received vs. Rejected) to maintain absolute stock integrity across production checkpoints. |

---

## 4. Technical Architecture & Design Directives
- **Backend Architecture:** Built on Django, utilizing strong relational schema rules (`ForeignKey`, `OneToOneField`) and signals/service functions (`merge_bom_component_details`, `sync_bom_worker_allocations`) to ensure cascading changes and real-time data synchronizations.
- **Frontend Design System:** Glassmorphism UI styled with sleek, customized Tailwind-complementary HSL palettes, vivid alerts, micro-animations, and drawer layouts.
- **SEO & Search Standards:** Optimized dynamic meta titles and global search indexes via vanilla Javascript triggers (`runGlobalSearch`).

---

## 5. Verification & Quality Standards
- **Automated Test Coverage:** Complete Django test modules verifying inventory, BOM creation, and labor ledger rate mappings.
- **UI Compilation Validation:** Continuous validation of template syntax, ensuring no unparsed template tags (`{{ ... }}`) exist in the production frontend code.
