#!/bin/sh
# Renders ADMIN_ALLOWED_CIDRS (spec §14.17) into an Nginx `geo` block at container start.
# Run by the image's /docker-entrypoint.sh before Nginx starts; nginx.conf includes the output.
# Fails closed: an entry with anything but address characters stops the container, and Nginx
# itself refuses to start on an entry that is not a valid address or network.
set -eu
set -f  # entries are never glob-expanded

out_dir=/tmp/nginx-generated
out="$out_dir/admin-allow.conf"
mkdir -p "$out_dir"

entries=$(printf '%s' "${ADMIN_ALLOWED_CIDRS:-}" | tr ',' ' ')

{
    echo "# Generated at container start from ADMIN_ALLOWED_CIDRS; do not edit."
    echo 'geo $devsync_admin_net_ok {'
    if [ -z "$(printf '%s' "$entries" | tr -d ' \t')" ]; then
        echo '    default 1;  # empty list: every network (admin still needs role + TOTP)'
    else
        echo '    default 0;'
        for entry in $entries; do
            case "$entry" in
                *[!0-9A-Fa-f:./]*)
                    echo "ADMIN_ALLOWED_CIDRS: invalid entry; refusing to start" >&2
                    exit 1
                    ;;
            esac
            echo "    $entry 1;"
        done
    fi
    echo '}'
} > "$out.tmp"
mv "$out.tmp" "$out"
