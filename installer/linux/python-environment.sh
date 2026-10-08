#!/usr/bin/env bash
# Keep the packaged interpreter independent of a host Python installation.
unset PYTHONHOME PYTHONPATH
export PYTHONNOUSERSITE=1
export PYTHONUTF8=1
if [[ -z "${SSL_CERT_FILE:-}" ]]; then
    for scott_ca in /etc/ssl/certs/ca-certificates.crt /etc/pki/tls/certs/ca-bundle.crt /etc/ssl/cert.pem; do
        if [[ -f "$scott_ca" ]]; then
            export SSL_CERT_FILE="$scott_ca"
            break
        fi
    done
    unset scott_ca
fi
