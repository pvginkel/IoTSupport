# Hobby Electronics Inventory — Product Brief

## 1) What this app is for

Keep track of hobby electronics parts so you always know **what you have**, **where it is**, and **how to get more**. It stays simple, fast, and focused on labeling, storage, and finding things.

## 2) Who will use it

* **You** (single user). No login required.

## 3) What it will do (scope)

* Add and label parts with a short, unique ID.
* Organize storage into **numbered boxes** with **numbered locations** inside.
* Track **how many** you have and **where** it lives (supports multiple locations per part).
* Keep **documentation** (PDFs, images, links) attached to each part and viewable in the app.
* Maintain a **shopping list** for parts you don’t have yet (or ran out of).
* Suggest **where to put things** to keep similar items together.
* Propose **reorganization plans** when you want to tidy up.
* Offer **AI helpers** to auto-tag, pull in documentation, and prefill details from a photo or part number.
* Support **projects/kits**: plan builds, see what’s missing, and add gaps to the shopping list.

## 4) Out of scope

* No PCB CAD integration (not in later phases either).
* No backups/exports (you’ll handle database backups yourself).
* No pricing, condition, or reorder thresholds.

## 5) Storage model (plain language)

**Boxes & locations**

* Boxes are **numbers**: Box “1”, Box “2”, …
* Each box has a set of **numbered locations** laid out **left-to-right, top-to-bottom**.
* A specific slot is written as **BOX-LOCATION** (e.g., “7-3” means Box 7, Location 3).
* Locations are generated in sequence for each box (e.g., 1..60). The UI shows them as a simple list of locations.

**Parts**

* **ID** (auto-generated, used for labels).
* **Manufacturer code** (e.g., “OMRON G5Q-1A4”).
* **Type** (category): Relay, Power Module, Sensor, Connector, LED, Resistor, Capacitor, IC, Microcontroller, Cable, Mechanical, etc. (You’ll manage the list in the frontend.)
* **Description** (free text).
* **Quantity** (total on hand).
* **Locations**: one **part** can live in **multiple locations** at once, each with its own quantity.

  * When total quantity reaches **zero**, all location assignments are **cleared** and those locations become **reusable**.
  * The **part itself is never deleted**; its documentation stays.
* **Image** (a main photo; you can add via mobile camera).
* **Tags** (auto-generated + editable; e.g., “SMD”, “0603”, “5V”, “THT”—we’ll start with tags; we may promote “package size” and “key ratings” to first-class fields later).
* **Seller** and **seller product page link** (single set; you can update it).

**Documentation**

* Multiple items per part: **PDFs**, **images**, and **links**.
* PDFs and images are **uploaded** and **viewable** directly in the app.
* No separate datasheet link field; attach the PDF itself.

**Change history (lightweight)**

* For quantity changes: keep a **timestamp** of added/removed amounts (no extra notes required).
* When adding parts, you can also add docs and update seller details in the same flow.

**Shopping list**

* A simple list of parts you want to acquire.
* Can include parts that **don’t exist in storage** yet (no location).
* When you receive stock, you convert shopping list entries into **real inventory** with suggested locations.

**Projects (kits)**

* Create a project and add **required parts + quantities**.
* See stock coverage immediately (enough / partial / missing).
* Add missing items straight to the shopping list.
* When you “build,” the app can **deduct** quantities from chosen locations.

## 6) IDs & labeling

* **Default format:** 4 uppercase letters (e.g., “BZQP”). That’s 26⁴ = **456,976** unique IDs—plenty.
* The app guarantees **uniqueness**; if there’s a collision, it generates another.
* **Label content:** the **ID as text** (no QR codes required; optional 1D barcode only if your printer supports it—text alone is fine).

## 7) Finding things (search)

* **One simple search box.**
  Type anything (part ID, manufacturer code, type, tag, words in the description, seller, file name).
  Results show parts, their quantities, and locations. (No advanced filters needed.)

## 8) Smart suggestions (how it helps you stay organized)

* **Location suggestions** (on add/receive):

  1. Prefer free locations **in boxes that already hold the same category**,
  2. else use a **designated** box for that category,
  3. else the **first free location** across all boxes (filling left-to-right, top-to-bottom).
* **Reorganization runs** (when you’re in the mood):

  * The app proposes a **step-by-step plan** to improve grouping and reduce spread:

    * Cluster by category (e.g., all resistors closer together),
    * Reduce the number of boxes each category spans,
    * Fill boxes in order (no gaps before moving to the next box),
    * Avoid excessive moves (e.g., suggest up to N moves total).
  * You can accept all, some, or none of the suggestions.

## 9) AI helpers (MVP)

* **Auto-tagging** from the description and manufacturer code.
* **Photo intake (mobile camera):** snap a picture of a bag/label; the app tries to **recognize the part number**, **suggest a category**, and **fetch a datasheet PDF** (which it **stores**). You can approve or edit before saving.

## 10) Key workflows (extended)

1. **Create a box**

   * Choose the number of slots (e.g., 60).
   * The app generates locations **1…60** (left-to-right, top-to-bottom).
   * You now have slots “1-1” to “1-60”, “2-1” to “2-60”, etc.

2. **Add a new part (fast flow)**

   * Snap photo (optional) → enter manufacturer code and short description → pick a type.
   * The app generates the **4-letter ID** and **auto-tags** from the text/photo; it tries to **attach the datasheet PDF**.
   * Quantity in hand? If yes, the app **suggests locations**; accept or change.
   * Add/confirm seller and product link.
   * Save → print small label with the ID.

3. **Receive items for an existing part**

   * Open the part → “Add stock” → enter amount.
   * The app suggests locations (preferring category groups and filling gaps).
   * (Optional) attach new documents (invoice PDF, extra photos).
   * Quantity history logs the timestamp.

4. **Use items**

   * Open the part → “Use X” → choose which location(s) to deduct from.
   * If total reaches **zero**, location links are **cleared** automatically; the part remains in the catalog with docs.

5. **Move items / split across locations**

   * Select a part → “Move” → pick source location and destination location(s).
   * Quick keypad to move quantities (e.g., move 50 from 3-12 to 3-18 & 4-1).

6. **Shopping list**

   * Add any catalogued part you plan to buy (create the part entry first if it is new).
   * When items arrive, convert the shopping list entry into inventory: the app suggests locations, attaches docs, and merges with the existing part record.

7. **Projects (kits)**

   * Create project → add required parts + quantities (you can add parts that aren’t in stock yet).
   * See coverage: “have enough / short by 20 / not in inventory.”
   * One click: add shortages to the shopping list.
   * When you build, confirm which locations to pull from; the app deducts quantities and updates history.

8. **Reorganization run**

   * Start run → app analyzes current layout and suggests a move list:

     * “Move 20 of Part ABCD to 2-14 to keep all relays in Box 2.”
   * You can apply moves one-by-one or all at once.

9. **Attach and view documents**

   * Open a part → “Add document” → upload PDF or image or paste a link.
   * PDFs and images are viewable inside the app (no download needed).

## 11) Success criteria

* Add a new part with location and label in **under 20 seconds**.
* Find any part using the single search box in **under 10 seconds**.
* Record stock changes in **under 5 seconds**.
* Reorg runs produce **clear, bite-sized move steps** you can apply quickly.

## 12) Nice touches (optional, not required)

* Show tiny **thumbnails** in search results.
* If your label printer supports it, allow **1D barcodes** (otherwise just text).
* A “category dashboard” that shows how many boxes each category spans (helps decide reorgs).

## 13) Minimal conceptual model (for understanding only)

* **Part**: ID, manufacturer code, type, description, image, tags, seller, seller link, docs, total quantity.
* **Box**: number (e.g., 7), capacity (e.g., 60 locations).
* **Location**: number within a box (e.g., 3).
* **Part–Location assignment**: a quantity of a part in a specific slot (e.g., Part ABCD → Box 7, Loc 3 → qty 120).
* **History**: timestamped adds/removes.
* **ShoppingListItem**: desired part (may or may not already exist), optional link to the eventual Part.
* **Project**: name + required (Part, qty). Build flow deducts from chosen locations.
