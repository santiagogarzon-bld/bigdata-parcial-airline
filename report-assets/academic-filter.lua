local mermaid_index = 0

local function pagebreak()
  return pandoc.RawBlock('openxml', '<w:p><w:r><w:br w:type="page"/></w:r></w:p>')
end

local function figure(path, caption)
  local image = pandoc.Image({pandoc.Str(caption)}, path, caption, {width = '6.4in'})
  return pandoc.Para({image})
end

function Header(el)
  local text = pandoc.utils.stringify(el.content)
  if el.level == 1 and text == 'Airline Reservation System' then
    return {}
  end
  if el.level == 2 and string.match(text, '^Big Data and Data Engineering Midterm') then
    return {}
  end
  if el.level == 2 and text == 'Executive summary' then
    return {pagebreak(), pandoc.Header(1, 'Abstract')}
  end
  if el.level == 2 and text == 'Submission checklist' then
    return {pagebreak(), pandoc.Header(1, 'Submission Readiness Checklist')}
  end
  if el.level == 3 and text == '8.2 Analytical model and ETL' then
    return {
      el,
      figure('build/report-assets/flujo-datos-analitica.png',
             'Figure 4. Analytical data flow from operational sources to dimensional facts.'),
      figure('build/report-assets/flujo-etl.png',
             'Figure 5. ETL execution, controls, reconciliation, and failure path.')
    }
  end
  return el
end

function CodeBlock(el)
  if not el.classes:includes('mermaid') then
    return el
  end
  mermaid_index = mermaid_index + 1
  if mermaid_index == 1 then
    return figure('build/report-assets/airline-oltp-erd.png',
                  'Figure 1. Transactional airline reservation entity-relationship model (Crow’s Foot).')
  elseif mermaid_index == 2 then
    return figure('build/report-assets/concurrency-flow.png',
                  'Figure 2. Pessimistic locking and all-or-nothing reservation behavior under contention.')
  else
    return figure('build/report-assets/arquitectura-aws.png',
                  'Figure 3. Deployed AWS architecture for the transactional application and analytical platform.')
  end
end

function Link(el)
  if not string.match(el.target, '^https?://') and not string.match(el.target, '^#') then
    el.target = '../' .. el.target
  end
  return el
end
