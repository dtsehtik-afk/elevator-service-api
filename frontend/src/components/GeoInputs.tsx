/**
 * Israeli city and street autocomplete inputs.
 *
 * CitySelect  — restricts input to known Israeli localities (gov API list).
 * StreetInput — suggests streets for the chosen city, allows free-text.
 */
import { useEffect, useState } from 'react'
import { Select, Autocomplete } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import client from '../api/client'

async function fetchCities(): Promise<string[]> {
  const { data } = await client.get('/geo/cities')
  return data as string[]
}

async function fetchStreets(city: string, q: string): Promise<string[]> {
  if (!city || q.length < 2) return []
  const { data } = await client.get('/geo/streets', { params: { city, q } })
  return data as string[]
}

/** City selector — only allows values from the Israeli localities list. */
export function CitySelect({
  value,
  onChange,
  required,
  label = 'עיר',
  size,
  w,
  style,
  disabled,
}: {
  value: string | null
  onChange: (v: string) => void
  required?: boolean
  label?: string
  size?: string
  w?: number | string
  style?: React.CSSProperties
  disabled?: boolean
}) {
  const { data: cities = [], isLoading } = useQuery<string[]>({
    queryKey: ['geo-cities'],
    queryFn: fetchCities,
    staleTime: Infinity,
  })

  return (
    <Select
      label={label}
      required={required}
      value={value || null}
      onChange={v => onChange(v ?? '')}
      data={cities.map(c => ({ value: c, label: c }))}
      searchable
      clearable={!required}
      nothingFoundMessage={isLoading ? 'טוען...' : 'לא נמצאה עיר'}
      placeholder="חפש עיר..."
      size={size as any}
      w={w}
      style={style}
      disabled={disabled}
    />
  )
}

/** Street autocomplete — suggests streets from the city, allows unlisted values. */
export function StreetInput({
  value,
  onChange,
  city,
  required,
  label = 'כתובת (רחוב + מספר)',
  placeholder = 'לדוגמה: הרצל 12',
  size,
  w,
  style,
  disabled,
}: {
  value: string
  onChange: (v: string) => void
  city?: string | null
  required?: boolean
  label?: string
  placeholder?: string
  size?: string
  w?: number | string
  style?: React.CSSProperties
  disabled?: boolean
}) {
  const [inputVal, setInputVal] = useState(value)

  // Keep local state in sync with external value (e.g. on form reset)
  useEffect(() => { setInputVal(value) }, [value])

  const { data: streets = [] } = useQuery<string[]>({
    queryKey: ['geo-streets', city, inputVal],
    queryFn: () => fetchStreets(city || '', inputVal),
    enabled: !!city && inputVal.length >= 2,
    staleTime: 5 * 60 * 1000,
  })

  return (
    <Autocomplete
      label={label}
      required={required}
      value={inputVal}
      onChange={v => { setInputVal(v); onChange(v) }}
      data={streets}
      placeholder={placeholder}
      size={size as any}
      w={w}
      style={style}
      disabled={disabled}
    />
  )
}
