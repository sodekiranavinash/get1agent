package model

import "strings"

type Request struct {
	URL       string   `json:"url"`
	URLs      []string `json:"urls"`
	Arguments *Request `json:"arguments,omitempty"`
	Name      string   `json:"name,omitempty"`
}

func (r Request) ResolveURLs() []string {
	out := collectURLs(r.URL, r.URLs)
	if len(out) > 0 {
		return out
	}
	if r.Arguments != nil {
		return collectURLs(r.Arguments.URL, r.Arguments.URLs)
	}
	return nil
}

func collectURLs(single string, list []string) []string {
	out := make([]string, 0, 1+len(list))
	if u := strings.TrimSpace(single); u != "" {
		out = append(out, u)
	}
	for _, u := range list {
		if u = strings.TrimSpace(u); u != "" {
			out = append(out, u)
		}
	}
	return out
}

type Response struct {
	OK    bool       `json:"ok"`
	Error *ErrorBody `json:"error,omitempty"`
	Items []Item     `json:"items"`
}

type Item struct {
	OK               bool       `json:"ok"`
	SourceURL        string     `json:"sourceUrl,omitempty"`
	Error            *ErrorBody `json:"error,omitempty"`
	ExtractedChallan `json:",inline"`
}

type ErrorBody struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

type ExtractedChallan struct {
	IssuingAuthority  string    `json:"issuingAuthority"`
	OfficeName        string    `json:"officeName"`
	ChallanDate       string    `json:"challanDate"`
	ChallanDateISO    string    `json:"challanDateIso"`
	VehicleClass      string    `json:"vehicleClass"`
	VehicleNo         string    `json:"vehicleNo"`
	ChallanNo         string    `json:"challanNo"`
	LGDCode           string    `json:"lgdCode"`
	DLNo              string    `json:"dlNo"`
	PlaceOfIncident   string    `json:"placeOfIncident"`
	DocumentImpounded string    `json:"documentImpounded"`
	OwnerName         string    `json:"ownerName"`
	OwnerAddress      string    `json:"ownerAddress"`
	DriverName        string    `json:"driverName"`
	FatherName        string    `json:"fatherName"`
	EngineNo          string    `json:"engineNo"`
	ChassisNo         string    `json:"chassisNo"`
	ViolatorContactNo string    `json:"violatorContactNo"`
	ReceivedAmountInr *int      `json:"receivedAmountInr"`
	ReceiptDate       string    `json:"receiptDate"`
	Remarks           string    `json:"remarks"`
	Offences          []Offence `json:"offences"`
	Officer           Officer   `json:"officer"`
	Images            Images    `json:"images"`
}

type Offence struct {
	SrNo              int    `json:"srNo"`
	Offence           string `json:"offence"`
	MVAct             string `json:"mvAct"`
	CompoundingFeeInr int    `json:"compoundingFeeInr"`
	OffenceType       string `json:"offenceType"`
}

type Officer struct {
	Name  string `json:"name"`
	Email string `json:"email"`
	Rank  string `json:"rank"`
}

type Images struct {
	Evidence []string `json:"evidence"`
	Map      string   `json:"map"`
	QR       string   `json:"qr"`
	All      []string `json:"all"`
}
