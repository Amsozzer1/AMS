"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API, type Spool } from "@/api";

/** All three row actions (edit grams / archive / delete) and their state.
 *
 *  Kept together because they share one invariant: only ONE action's error may be visible at
 *  a time, so every action clears the others before it runs. Splitting them into separate
 *  hooks would lose that. A view-local hook, so it lives in this component's `_helpers`
 *  rather than the app-wide `hooks/`. */
export function useSpoolRowActions(s: Spool, title: string, onRefresh: () => void) {
  const [editing, setEditing] = useState(false);
  const [gramsDraft, setGramsDraft] = useState("");
  const [editBusy, setEditBusy] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [archiveBusy, setArchiveBusy] = useState(false);
  const [archiveError, setArchiveError] = useState<string | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const clearErrors = useCallback(() => {
    setEditError(null);
    setArchiveError(null);
    setDeleteError(null);
  }, []);

  const startEdit = useCallback(() => {
    setGramsDraft(typeof s.remaining_g === "number" ? String(Math.round(s.remaining_g)) : "");
    setEditError(null);
    setEditing(true);
  }, [s.remaining_g]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const cancelEdit = useCallback(() => {
    setEditing(false);
    setEditError(null);
  }, []);

  const submitEdit = useCallback(async () => {
    const val = parseFloat(gramsDraft);
    if (isNaN(val) || val < 0) {
      setEditError("Enter a valid non-negative number.");
      return;
    }
    clearErrors();
    setEditBusy(true);
    try {
      await API.spools.update(s.id, { remaining_g: val });
      setEditing(false);
      onRefresh();
    } catch (err) {
      setEditError(err instanceof Error ? err.message : String(err));
    } finally {
      setEditBusy(false);
    }
  }, [s.id, gramsDraft, onRefresh, clearErrors]);

  const doArchive = useCallback(async () => {
    clearErrors();
    setArchiveBusy(true);
    try {
      await API.spools.update(s.id, { archived: true });
      onRefresh();
    } catch (err) {
      setArchiveError(err instanceof Error ? err.message : String(err));
    } finally {
      setArchiveBusy(false);
    }
  }, [s.id, onRefresh, clearErrors]);

  const doDelete = useCallback(async () => {
    if (!window.confirm(`Delete spool "${title}"? This cannot be undone.`)) return;
    clearErrors();
    setDeleteBusy(true);
    try {
      await API.spools.delete(s.id);
      onRefresh();
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : String(err));
    } finally {
      setDeleteBusy(false);
    }
  }, [s.id, title, onRefresh, clearErrors]);

  return {
    editing,
    gramsDraft,
    setGramsDraft,
    inputRef,
    editBusy,
    startEdit,
    submitEdit,
    cancelEdit,
    archiveBusy,
    doArchive,
    deleteBusy,
    doDelete,
    rowError: editError || archiveError || deleteError,
  };
}
