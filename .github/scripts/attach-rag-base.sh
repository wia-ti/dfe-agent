#!/usr/bin/env bash
# Base RAG nas releases do semantic-release (Sprint 20).
#
#   attach-rag-base.sh --verify   verifyConditionsCmd: roda ANTES de qualquer
#                                 publicacao; falha se a `rag-base` nao bater
#                                 com storage/dfe.db.gz.sha256.
#   attach-rag-base.sh <tag>      successCmd: copia dfe.db.gz(+sha) da
#                                 `rag-base` para a release <tag>.
#
# O repo versiona so' o sha; o .gz vive na release rolante `rag-base`
# (publicada por `/deploy --base`).
set -euo pipefail

MODE="${1:?uso: attach-rag-base.sh --verify | <tag>}"
BASE_TAG="${RAG_BASE_TAG:-rag-base}"
TRACKED_SHA_FILE="storage/dfe.db.gz.sha256"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# 0 = existe, 1 = nao existe; qualquer outro erro do gh aborta.
base_exists() {
  local out
  if out="$(gh release view "$BASE_TAG" --json tagName 2>&1)"; then
    return 0
  fi
  if grep -qi "release not found" <<<"$out"; then
    return 1
  fi
  echo "::error::falha ao consultar a release $BASE_TAG: $out"
  exit 1
}

if ! base_exists; then
  echo "::warning::release $BASE_TAG nao existe; a release sai sem base RAG (rode /deploy --base)"
  exit 0
fi

gh release download "$BASE_TAG" -p dfe.db.gz -p dfe.db.gz.sha256 -D "$WORK"

published="$(tr -d '[:space:]' < "$WORK/dfe.db.gz.sha256")"
actual="$(sha256sum "$WORK/dfe.db.gz" | cut -d' ' -f1)"
tracked="$(tr -d '[:space:]' < "$TRACKED_SHA_FILE")"

if [ "$actual" != "$published" ]; then
  echo "::error::dfe.db.gz da $BASE_TAG corrompido (sha $actual != $published)"
  exit 1
fi
if [ "$published" != "$tracked" ]; then
  echo "::error::$BASE_TAG ($published) difere de $TRACKED_SHA_FILE ($tracked); rode /deploy --base"
  exit 1
fi

if [ "$MODE" = "--verify" ]; then
  echo "base RAG $published confere com $TRACKED_SHA_FILE"
  exit 0
fi

gh release upload "$MODE" "$WORK/dfe.db.gz" "$WORK/dfe.db.gz.sha256" --clobber
echo "base RAG $published anexada a $MODE"
