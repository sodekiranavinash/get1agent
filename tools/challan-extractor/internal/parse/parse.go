package parse

import (
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"
	"unicode"

	"github.com/PuerkitoBio/goquery"

	"get1agent/tools/challan-extractor/internal/model"
)

const maxEvidence = 4

var (
	reWS             = regexp.MustCompile(`\s+`)
	reEmail          = regexp.MustCompile(`[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}`)
	reReceivedAmount = regexp.MustCompile(`Received Amount\s+Rs\s+(\d+)`)
	reRemarks        = regexp.MustCompile(`Remarks:\s*(.+)`)
	reReceiptDate    = regexp.MustCompile(`Date\s+(\d{2}-\d{2}-\d{4})`)
	reChallanDate    = regexp.MustCompile(`(\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}:\d{2})`)
	ist              = time.FixedZone("IST", 5*60*60+30*60)
)

func HTML(raw []byte, pageURL string) (model.ExtractedChallan, error) {
	doc, err := goquery.NewDocumentFromReader(strings.NewReader(string(raw)))
	if err != nil {
		return model.ExtractedChallan{}, err
	}

	out := model.ExtractedChallan{
		Offences: []model.Offence{},
		Images: model.Images{
			Evidence: []string{},
			All:      []string{},
		},
	}

	base, _ := url.Parse(pageURL)
	extractImages(doc, base, &out)
	extractLabelValues(doc, &out)
	extractHeader(doc, &out)
	extractImpounded(doc, &out)
	extractOffences(doc, &out)
	extractOfficerAndPayment(doc, &out)
	out.ChallanDateISO = toISTISO(out.ChallanDate)
	return out, nil
}

func extractImages(doc *goquery.Document, base *url.URL, out *model.ExtractedChallan) {
	seen := map[string]struct{}{}
	doc.Find("img").Each(func(_ int, s *goquery.Selection) {
		src, ok := s.Attr("src")
		if !ok {
			return
		}
		abs := absolutize(base, strings.TrimSpace(src))
		if abs == "" {
			return
		}
		lower := strings.ToLower(abs)
		if _, dup := seen[lower]; dup {
			return
		}
		seen[lower] = struct{}{}
		out.Images.All = append(out.Images.All, abs)

		switch {
		case strings.Contains(lower, "qrcode"):
			if out.Images.QR == "" {
				out.Images.QR = abs
			}
		case strings.Contains(lower, "staticmap") || strings.Contains(lower, "maps.googleapis.com") || strings.Contains(lower, "maps.google"):
			if out.Images.Map == "" {
				out.Images.Map = abs
			}
		case isPlaceholderOrLogo(lower):
			// skip evidence
		case isEvidence(lower):
			if len(out.Images.Evidence) < maxEvidence {
				out.Images.Evidence = append(out.Images.Evidence, abs)
			}
		}
	})
}

func isPlaceholderOrLogo(lower string) bool {
	skip := []string{
		"/www/img/no_image.png",
		"/www/img/gov.png",
		"/www/img/logo1.png",
		"/www/img/nic_logo.png",
		"no_image.png",
	}
	for _, s := range skip {
		if strings.Contains(lower, s) {
			return true
		}
	}
	return false
}

func isEvidence(lower string) bool {
	if strings.Contains(lower, "challans_downloaded_images") {
		return true
	}
	for _, ext := range []string{".jpeg", ".jpg", ".png", ".webp"} {
		if strings.Contains(lower, ext) && !isPlaceholderOrLogo(lower) &&
			!strings.Contains(lower, "qrcode") &&
			!strings.Contains(lower, "staticmap") {
			return true
		}
	}
	return false
}

func extractLabelValues(doc *goquery.Document, out *model.ExtractedChallan) {
	doc.Find("div").Each(func(_ int, s *goquery.Selection) {
		class, _ := s.Attr("class")
		if !strings.Contains(class, "col-xs") {
			return
		}
		label := norm(s.Text())
		if label == "" {
			return
		}
		val := siblingValue(s)
		if val == "" || val == "........." || val == "........" {
			// still assign placeholders when they are the real value (chassis etc.)
			if val == "" {
				return
			}
		}
		assign(out, label, val)
	})
}

func siblingValue(s *goquery.Selection) string {
	n := s.Next()
	if n.Length() == 0 {
		return ""
	}
	b := strings.TrimSpace(n.Find("b").First().Text())
	if b != "" {
		return collapse(b)
	}
	return collapse(n.Text())
}

func assign(out *model.ExtractedChallan, label, val string) {
	switch {
	case containsFold(label, "Challan Date"):
		if out.ChallanDate == "" {
			out.ChallanDate = val
		}
	case containsFold(label, "Vehicle Class"):
		out.VehicleClass = val
	case containsFold(label, "Vehicle no"):
		out.VehicleNo = val
	case containsFold(label, "Challan no"):
		out.ChallanNo = val
	case containsFold(label, "LGD Code"):
		out.LGDCode = val
	case containsFold(label, "DL no"):
		out.DLNo = val
	case containsFold(label, "Place of incident"):
		out.PlaceOfIncident = val
	case containsFold(label, "Owner's Name") || containsFold(label, "Owner’s Name"):
		out.OwnerName = val
	case containsFold(label, "Owner's") && containsFold(label, "Address"):
		out.OwnerAddress = val
	case containsFold(label, "Driver's name") || containsFold(label, "Driver’s name"):
		out.DriverName = val
	case containsFold(label, "Father's name") || containsFold(label, "Father’s name"):
		out.FatherName = val
	case containsFold(label, "Engine no"):
		out.EngineNo = val
	case containsFold(label, "Chassis no"):
		out.ChassisNo = val
	case containsFold(label, "Violator Contact"):
		out.ViolatorContactNo = val
	}
}

func extractHeader(doc *goquery.Document, out *model.ExtractedChallan) {
	doc.Find("b").Each(func(_ int, s *goquery.Selection) {
		t := collapse(s.Text())
		if out.IssuingAuthority == "" && strings.Contains(t, "Traffic Police") {
			out.IssuingAuthority = trafficPoliceLine(t)
		}
	})
	full := collapse(doc.Text())
	if i := strings.Index(full, "Office Name"); i >= 0 {
		rest := full[i:]
		if j := strings.Index(rest, ":"); j >= 0 {
			rest = strings.TrimSpace(rest[j+1:])
			out.OfficeName = firstToken(rest)
		}
	}
}

func trafficPoliceLine(t string) string {
	idx := strings.Index(t, "Traffic Police")
	if idx < 0 {
		return collapse(t)
	}
	line := t[idx:]
	if end := strings.Index(line, "Infringement"); end > 0 {
		line = line[:end]
	}
	return strings.TrimSpace(line)
}

func firstToken(s string) string {
	fields := strings.Fields(s)
	if len(fields) == 0 {
		return ""
	}
	return fields[0]
}

func extractImpounded(doc *goquery.Document, out *model.ExtractedChallan) {
	full := collapse(doc.Text())
	idx := strings.Index(full, "Document Impounded")
	if idx < 0 {
		return
	}
	rest := strings.TrimSpace(full[idx+len("Document Impounded"):])
	rest = strings.TrimLeft(rest, ":")
	rest = strings.TrimSpace(rest)
	out.DocumentImpounded = cutAtDevanagariOrMarker(rest)
}

func cutAtDevanagariOrMarker(s string) string {
	cut := len(s)
	for i, r := range s {
		if r >= 0x0900 && r <= 0x097F {
			cut = i
			break
		}
	}
	s = strings.TrimSpace(s[:cut])
	if i := strings.Index(strings.ToLower(s), "offences charged"); i >= 0 {
		s = strings.TrimSpace(s[:i])
	}
	return s
}

func extractOffences(doc *goquery.Document, out *model.ExtractedChallan) {
	doc.Find("table").Each(func(_ int, table *goquery.Selection) {
		head := collapse(table.Find("thead").Text())
		if !strings.Contains(head, "Offences Charged") {
			return
		}
		table.Find("tbody tr").Each(func(_ int, tr *goquery.Selection) {
			tds := tr.Find("td")
			if tds.Length() < 5 {
				return
			}
			cells := make([]string, 0, tds.Length())
			tds.Each(func(_ int, td *goquery.Selection) {
				cells = append(cells, collapse(td.Text()))
			})
			sr := atoiPrefix(cells[0])
			fee, _ := strconv.Atoi(strings.TrimSpace(cells[3]))
			out.Offences = append(out.Offences, model.Offence{
				SrNo:              sr,
				Offence:           cells[1],
				MVAct:             cells[2],
				CompoundingFeeInr: fee,
				OffenceType:       cells[4],
			})
		})
	})
}

func extractOfficerAndPayment(doc *goquery.Document, out *model.ExtractedChallan) {
	full := collapse(doc.Text())
	if m := reEmail.FindString(full); m != "" {
		out.Officer.Email = m
	}
	if i := strings.Index(full, "Name and signature of Officer"); i >= 0 {
		rest := strings.TrimSpace(full[i+len("Name and signature of Officer"):])
		line := rest
		if out.Officer.Email != "" {
			if j := strings.Index(rest, out.Officer.Email); j > 0 {
				line = strings.TrimSpace(rest[:j])
			}
		}
		line = strings.Trim(line, "()")
		out.Officer.Name = strings.TrimSpace(strings.Trim(line, "() "))
	}
	ranks := []string{"SUB INSPECTOR", "INSPECTOR", "HEAD CONSTABLE", "CONSTABLE", "CIRCLE INSPECTOR"}
	upper := strings.ToUpper(full)
	for _, r := range ranks {
		if strings.Contains(upper, r) {
			out.Officer.Rank = r
			break
		}
	}
	if m := reReceivedAmount.FindStringSubmatch(full); len(m) == 2 {
		n, _ := strconv.Atoi(m[1])
		out.ReceivedAmountInr = &n
	}
	if m := reRemarks.FindStringSubmatch(full); len(m) == 2 {
		out.Remarks = cutAtDevanagariOrMarker(m[1])
		if i := strings.Index(out.Remarks, "Name and signature"); i > 0 {
			out.Remarks = strings.TrimSpace(out.Remarks[:i])
		}
	}
	if m := reReceiptDate.FindStringSubmatch(full); len(m) == 2 {
		out.ReceiptDate = m[1]
	}
	if out.ChallanDate == "" {
		if m := reChallanDate.FindStringSubmatch(full); len(m) == 2 {
			out.ChallanDate = m[1]
		}
	}
}

func toISTISO(d string) string {
	d = strings.TrimSpace(d)
	if d == "" {
		return ""
	}
	t, err := time.ParseInLocation("02-01-2006 15:04:05", d, ist)
	if err != nil {
		return ""
	}
	return t.Format(time.RFC3339)
}

func absolutize(base *url.URL, src string) string {
	if src == "" {
		return ""
	}
	u, err := url.Parse(src)
	if err != nil {
		return ""
	}
	if u.Scheme == "http" || u.Scheme == "https" {
		u.Scheme = "https"
		return u.String()
	}
	if strings.EqualFold(u.Scheme, "HTTPS") || strings.EqualFold(u.Scheme, "HTTP") {
		u.Scheme = "https"
		return u.String()
	}
	if base == nil {
		return src
	}
	return base.ResolveReference(u).String()
}

func collapse(s string) string {
	return strings.TrimSpace(reWS.ReplaceAllString(s, " "))
}

func norm(s string) string {
	return collapse(s)
}

func containsFold(hay, needle string) bool {
	return strings.Contains(strings.ToLower(hay), strings.ToLower(needle))
}

func atoiPrefix(s string) int {
	var b strings.Builder
	for _, r := range s {
		if unicode.IsDigit(r) {
			b.WriteRune(r)
			continue
		}
		if b.Len() > 0 {
			break
		}
	}
	n, _ := strconv.Atoi(b.String())
	return n
}
