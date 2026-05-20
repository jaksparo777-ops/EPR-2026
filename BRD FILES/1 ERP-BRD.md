# Foundry ERP — Business Requirements Document

## 1. Project Overview

Foundry ERP is a small Django-based inventory and manufacturing tracking application designed for a metal foundry business. It supports:
- casting stock entry
- stock tracking across manufacturing stages
- master data management for items, clients, and workers
- dashboard summaries for stock quantities and weights

The system is implemented as a Django project in `core/`, with a single application called `inventory`.

## 2. Architecture

### Framework and runtime
- Django web framework
- SQLite database (`core/db.sqlite3`)
- Templates rendered using Django template engine
- No external frontend framework; UI uses plain HTML, CSS, and minimal JavaScript

### Application structure
- `core/core/settings.py`: project settings
- `core/core/urls.py`: root URL configuration using `inventory.urls`
- `core/inventory/models.py`: database tables and business entities
- `core/inventory/views.py`: page controllers and workflow logic
- `core/inventory/forms.py`: Django ModelForm for casting entry
- `core/templates/`: UI templates and shared layout

## 3. Data Model

### Models

#### Item
Represents an inventory item or product.
- `code`, `name`
- `category`: Brass, Mortar, Pestle, Chopping Board, Other
- variant, item_type
- `weight_per_piece`, `lot_size`, `lot_with_box`
- `process`: machining, polishing, packaging
- `rate_per_piece`
- `active`, `created_at`

#### Client
Represents a customer or buyer.
- `name`, `phone`, `city`
- `active`, `created_at`

#### Worker
Represents a job worker or contractor.
- `name`, `process`
- `phone`, `active`, `created_at`

#### Warehouse
Represents a stock location.
- `name`, `code`
- created by default: `CASTING`, `MACHINING`, `READY`

#### StockTransaction
Represents movement or record of stock through the workflow.
- `item`, `transaction_type`
- `from_warehouse`, `to_warehouse`
- `worker`, `client`
- `heat_no`, `quantity`, `weight`, `lot_quantity`, `notes`
- `created_at`

Supported transaction types:
- casting_entry
- machining_issue
- machining_receive
- polishing_issue
- polishing_receive
- dispatch

## 4. Business Processes

### 4.1 Dashboard

The dashboard page (`/`) shows live stock metrics for each warehouse stage:
- Casting Stock
- Machining Stock
- Ready Stock

Each stage reports total piece count and weight.

### 4.2 Casting Entry

The casting page (`/casting/`) supports:
- creating a new casting stock entry
- viewing recent entries
- viewing all entries
- filtering summary data by date range
- summary totals by heat count, pieces, weight
- summary breakdown by item and by client

It also includes client and item selection, automatic weight calculation from selected item and entered pieces, and notes entry.

### 4.3 Master Data

The master data page (`/master-data/`) provides tabs for:
- Items
- Clients
- Workers

Each tab supports adding new records and shows all existing records.

## 5. System Flows

### Add master data
1. Navigate to `/master-data/`
2. Choose Items / Clients / Workers tab
3. Submit the form to create the entity

### Create casting entry
1. Navigate to `/casting/`
2. Enter heat number, select client and item
3. Enter quantity or let the page auto-calculate weight
4. Submit to save a new `casting_entry`

### View summaries
- `All Entries` tab displays every casting entry
- `Summary` tab filters by date range and groups totals by item and client

## 6. Key Notes and Implementation Observations

### Default warehouses
The application ensures three default warehouses exist by calling `create_default_warehouses()` from the dashboard and casting entry views.

### Current route coverage
Registered routes in `core/inventory/urls.py`:
- `/` -> dashboard
- `/casting/` -> casting entry
- `/master-data/` -> master data

### Unused or partially connected pages
The base template includes sidebar links for:
- `/casting-stock/`
- `/issue-machining/`
- `/machining-stock/`

Those routes are not present in `inventory/urls.py`, so these pages would currently return 404 if clicked.

### Data binding mismatch
In `core/templates/casting.html`, the form fields use names like `heat_number`, but the `CastingEntryForm` and model use `heat_no`. This mismatch may prevent the form from saving heat data correctly and appears to be a bug.

### Dashboard data gap
The dashboard template uses `item_stock` for the casting stock breakdown, but the dashboard view does not populate that context variable. That is another inconsistency to resolve.

## 7. Deployment and Runtime

### Configuration
- `DEBUG = True`
- SQLite database stored at `core/db.sqlite3`
- `TIME_ZONE = 'Asia/Kolkata'`

### Installed apps
- `django.contrib.admin`
- `django.contrib.auth`
- `django.contrib.contenttypes`
- `django.contrib.sessions`
- `django.contrib.messages`
- `django.contrib.staticfiles`
- `inventory`

## 8. Recommended Next Improvements

- Add missing URL routes for `/casting-stock/`, `/issue-machining/`, and `/machining-stock/`
- Fix the form field name mismatch between `heat_number` and `heat_no`
- Add stock calculation pages for machining and ready stock stages
- Add search and pagination for large entry tables
- Convert master data forms to ModelForms for stronger validation

---

Generated from code inspection of `core/inventory/` and `core/core/` files.
