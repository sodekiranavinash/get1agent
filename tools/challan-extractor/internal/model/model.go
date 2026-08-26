package model

import "strings"

type Request struct {
	URL       string   `json:"url"`
	Arguments *Request `json:"arguments,omitempty"`
	Name      string   `json:"name,omitempty"`
}

func (r Request) ResolveURL() string {
	if u := strings.TrimSpace(r.URL); u != "" {
		return u
	}
	if r.Arguments != nil {
		return strings.TrimSpace(r.Arguments.URL)
	}
	return ""
}

type Response struct {
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
