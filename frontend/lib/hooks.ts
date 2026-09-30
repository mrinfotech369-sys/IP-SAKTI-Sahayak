'use client';

import { useQuery } from '@tanstack/react-query';
import { get } from './api';
import type { InnovationDetail } from './types';

export function useInnovation(id: string) {
  return useQuery({ queryKey: ['innovation', id], queryFn: () => get<InnovationDetail>(`/innovations/${id}`) });
}

/** Query scoped to an innovation (key includes the id so re-analysis invalidates it). */
export function useInnovationData<T = any>(id: string, sub: string, enabled = true) {
  return useQuery({ queryKey: ['innovation', id, sub], queryFn: () => get<T>(`/innovations/${id}/${sub}`), enabled });
}
