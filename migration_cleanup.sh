#!/bin/bash
# Comprehensive migration cleanup script to remove all references to old project

set -e

OLD_PROJECT="sapphireinfinite"
OLD_PROJECT_NUM="342943608894"
NEW_PROJECT="sapphireinfinite"
NEW_PROJECT_NUM="342943608894"

echo "🔍 SAPPHIRE Migration Cleanup"
echo "============================="
echo ""
echo "Old Project: $OLD_PROJECT ($OLD_PROJECT_NUM)"
echo "New Project: $NEW_PROJECT ($NEW_PROJECT_NUM)"
echo ""

# Find all files with old references
echo "1️⃣ Scanning for old project references..."
echo ""

FILES_WITH_OLD_PROJECT=$(grep -r "$OLD_PROJECT" --include="*.sh" --include="*.md" --include="*.yaml" --include="*.yml" --include="*.py" --include="*.ts" --include="*.tsx" --include="*.js" --include="*.json" . 2>/dev/null | grep -v node_modules | grep -v ".git" | cut -d: -f1 | sort -u || true)

FILES_WITH_OLD_NUM=$(grep -r "$OLD_PROJECT_NUM" --include="*.sh" --include="*.md" --include="*.yaml" --include="*.yml" --include="*.py" --include="*.ts" --include="*.tsx" --include="*.js" --include="*.json" . 2>/dev/null | grep -v node_modules | grep -v ".git" | cut -d: -f1 | sort -u || true)

echo "Files with '$OLD_PROJECT': $(echo "$FILES_WITH_OLD_PROJECT" | wc -l | tr -d ' ')"
echo "Files with '$OLD_PROJECT_NUM': $(echo "$FILES_WITH_OLD_NUM" | wc -l | tr -d ' ')"
echo ""

# Show what will be changed
if [ -n "$FILES_WITH_OLD_PROJECT" ]; then
    echo "Files containing '$OLD_PROJECT':"
    echo "$FILES_WITH_OLD_PROJECT" | head -10
    if [ $(echo "$FILES_WITH_OLD_PROJECT" | wc -l) -gt 10 ]; then
        echo "... and $(($(echo "$FILES_WITH_OLD_PROJECT" | wc -l) - 10)) more"
    fi
    echo ""
fi

if [ -n "$FILES_WITH_OLD_NUM" ]; then
    echo "Files containing '$OLD_PROJECT_NUM':"
    echo "$FILES_WITH_OLD_NUM" | head -10
    if [ $(echo "$FILES_WITH_OLD_NUM" | wc -l) -gt 10 ]; then
        echo "... and $(($(echo "$FILES_WITH_OLD_NUM" | wc -l) - 10)) more"
    fi
    echo ""
fi

echo "2️⃣ Checking GCP resources..."
echo ""

# Check if old project still exists
if gcloud projects describe "$OLD_PROJECT" &>/dev/null; then
    echo "  ⚠️  Old project '$OLD_PROJECT' still exists"
    echo "     Consider: gcloud projects delete $OLD_PROJECT (after verification)"
else
    echo "  ✅ Old project '$OLD_PROJECT' not found (may be deleted or inaccessible)"
fi
echo ""

# Check service accounts
echo "3️⃣ Service Account Check..."
OLD_SA="${OLD_PROJECT_NUM}-compute@developer.gserviceaccount.com"
NEW_SA="${NEW_PROJECT_NUM}-compute@developer.gserviceaccount.com"

if gcloud iam service-accounts describe "$OLD_SA" --project="$NEW_PROJECT" &>/dev/null 2>&1; then
    echo "  ⚠️  Old service account found in new project"
else
    echo "  ✅ Old service account not in new project"
fi
echo ""

echo "4️⃣ Summary of Changes Needed:"
echo ""
echo "  - Update documentation files (README, deployment guides)"
echo "  - Update script files (deployment, monitoring scripts)"
echo "  - Update configuration files (YAML, config files)"
echo "  - Update code references (Python, TypeScript)"
echo "  - Verify GCP resources are using new project"
echo "  - Check Cloud Run service URLs"
echo "  - Verify DNS and load balancer configurations"
echo ""

echo "5️⃣ Next Steps:"
echo ""
echo "  Run this script with --dry-run to see what would change:"
echo "    ./migration_cleanup.sh --dry-run"
echo ""
echo "  Or run with --apply to make changes:"
echo "    ./migration_cleanup.sh --apply"
echo ""

if [ "$1" == "--dry-run" ]; then
    echo "🔍 DRY RUN MODE - Showing what would be changed:"
    echo ""
    
    # Show sample replacements
    echo "Sample replacements:"
    echo "  '$OLD_PROJECT' → '$NEW_PROJECT'"
    echo "  '$OLD_PROJECT_NUM' → '$NEW_PROJECT_NUM'"
    echo "  'cloud-trader-$OLD_PROJECT_NUM' → 'cloud-trader-$NEW_PROJECT_NUM'"
    echo ""
    
elif [ "$1" == "--apply" ]; then
    echo "⚠️  APPLY MODE - Making changes..."
    echo ""
    read -p "Are you sure you want to proceed? (yes/no): " confirm
    
    if [ "$confirm" != "yes" ]; then
        echo "Aborted."
        exit 1
    fi
    
    # Make replacements
    echo "Updating files..."
    
    # Update project name
    find . -type f \( -name "*.sh" -o -name "*.md" -o -name "*.yaml" -o -name "*.yml" -o -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" -o -name "*.json" \) \
        -not -path "*/node_modules/*" \
        -not -path "*/.git/*" \
        -exec sed -i '' "s/$OLD_PROJECT/$NEW_PROJECT/g" {} +
    
    # Update project number in URLs (but be careful with service account emails)
    find . -type f \( -name "*.sh" -o -name "*.md" -o -name "*.yaml" -o -name "*.yml" -o -name "*.py" -o -name "*.ts" -o -name "*.tsx" -o -name "*.js" \) \
        -not -path "*/node_modules/*" \
        -not -path "*/.git/*" \
        -exec sed -i '' "s/-$OLD_PROJECT_NUM\./-$NEW_PROJECT_NUM./g" {} +
    
    echo "✅ Changes applied. Please review and test."
    echo ""
    echo "⚠️  IMPORTANT: Some files may need manual review:"
    echo "  - Service account emails (if they reference old project)"
    echo "  - Historical documentation (may want to keep for reference)"
    echo "  - Configuration files with project-specific settings"
    
else
    echo "ℹ️  No action taken. Use --dry-run or --apply to proceed."
fi

echo ""
echo "✅ Migration cleanup analysis complete"

