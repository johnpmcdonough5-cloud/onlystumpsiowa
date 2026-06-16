# OnlyStumps — static website

Stump grinding & removal site for eastern Iowa, built as plain HTML/CSS/JS so it can be hosted free on **GitHub Pages**. No build step, no framework.

## What's inside

```
onlystumps/
├── index.html                      Home
├── StumpGrinding/                  Stump Grinding (main)
│   ├── Residential/
│   ├── Commercial/
│   ├── Municipal/
│   ├── RaisedRoots/
│   └── IowaCostCalculator/         Interactive cost estimator
├── LandscapeRestoration/
├── Company/                        "Why OnlyStumps?"
├── StumpGrindingGallery/           Gallery
├── ServiceArea/                    Service area + 14 county subpages
│   ├── AllamakeeCounty/ ClaytonCounty/ DubuqueCounty/ JacksonCounty/
│   ├── JonesCounty/ LinnCounty/ CedarCounty/ JohnsonCounty/
│   ├── BentonCounty/ TamaCounty/ DelawareCounty/ BuchananCounty/
│   └── BlackHawkCounty/ GrundyCounty/
├── Blog/                           Blog index + 3 posts
├── Contact/
├── assets/css/style.css            All styling
├── assets/img/*.svg                Placeholder images (swap for real photos)
├── 404.html  robots.txt  .nojekyll
```

Every page mirrors the original site's URL structure (folder + `index.html` = clean URLs like `/StumpGrinding/Residential/`). All copy is original, written for OnlyStumps.

## Before you publish — 2 things to change

1. **Contact details.** Phone `(555) 123-4567` and email `hello@onlystumps.com` are placeholders. Find & replace them across all files.
2. **The quote form.** It posts to Formspree. Create a free form at https://formspree.io, then replace `your-form-id` in every `action="https://formspree.io/f/your-form-id"` with your real form ID. (Quickest: search the project for `your-form-id`.)

Optional: replace the SVG placeholder images in `assets/img/` with real job photos (keep the same filenames and they'll just work).

## Deploy to GitHub Pages

1. Create a new repository on GitHub (e.g. `onlystumps`).
2. Upload the **contents** of this folder to the repo root (so `index.html` is at the top level), or push with git:
   ```
   git init
   git add .
   git commit -m "OnlyStumps site"
   git branch -M main
   git remote add origin https://github.com/YOUR-USERNAME/onlystumps.git
   git push -u origin main
   ```
3. In the repo: **Settings → Pages → Source: Deploy from a branch → `main` / `root` → Save.**
4. Your site goes live at `https://YOUR-USERNAME.github.io/onlystumps/` in a minute or two.

### Using your own domain
In Settings → Pages, add your custom domain. GitHub creates a `CNAME` file; then point your domain's DNS at GitHub Pages per their instructions.

> The `.nojekyll` file is included so GitHub serves all folders as-is.
