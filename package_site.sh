#!/bin/bash
# Refresh the site/ folder with the latest dashboard + data for Netlify deploy.
# Drag site/ onto https://app.netlify.com/drop (or run `netlify deploy --prod`
# from inside site/ if you use the Netlify CLI).
cd "$(dirname "$0")"
mkdir -p site
cp index.html data.js site/
echo "site/ updated - data timestamp: $(grep -o '"generated": "[^"]*"' data.js | head -1)"
