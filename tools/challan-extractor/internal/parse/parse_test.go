package parse_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"get1agent/tools/challan-extractor/internal/parse"
)

func TestHTML_PrintPageFixture(t *testing.T) {
	raw, err := os.ReadFile(filepath.Join("..", "..", "testdata", "print-page.html"))
	if err != nil {
		t.Fatal(err)
	}

	got, err := parse.HTML(raw, "https://echallan.parivahan.gov.in/report/print-page?challan_no=token")
	if err != nil {
		t.Fatal(err)
	}

	assertEq(t, "issuingAuthority", got.IssuingAuthority, "Traffic Police Andhra Pradesh")
	assertEq(t, "officeName", got.OfficeName, "Kakinada")
	assertEq(t, "challanDate", got.ChallanDate, "26-04-2026 19:53:06")
	assertEq(t, "challanDateIso", got.ChallanDateISO, "2026-04-26T19:53:06+05:30")
	assertEq(t, "vehicleClass", got.VehicleClass, "M-Cycle/Scooter(2WN)")
	assertEq(t, "vehicleNo", got.VehicleNo, "AP40HP6758")
	assertEq(t, "challanNo", got.ChallanNo, "AP186219260426195306")
	assertEq(t, "lgdCode", got.LGDCode, "746")
	assertEq(t, "dlNo", got.DLNo, "No DL")
	if !strings.Contains(got.PlaceOfIncident, "Surya Rao Peta, Kakinada") {
		t.Fatalf("placeOfIncident = %q", got.PlaceOfIncident)
	}
	assertEq(t, "documentImpounded", got.DocumentImpounded, "No Document Impounded")
	assertEq(t, "ownerName", got.OwnerName, "S**E K***N A*****H")
	assertEq(t, "driverName", got.DriverName, "S**E K***N A*****H")
	assertEq(t, "engineNo", got.EngineNo, "CK4GS31*****")
	assertEq(t, "officer.email", got.Officer.Email, "kkd_ps2traffickkd_si2@echallan.appolice.gov.in")
	assertEq(t, "officer.rank", got.Officer.Rank, "SUB INSPECTOR")
	if !strings.Contains(got.Officer.Name, "A Satyanarayana_SI Traffic-II") {
		t.Fatalf("officer.name = %q", got.Officer.Name)
	}
	if got.ReceivedAmountInr == nil || *got.ReceivedAmountInr != 185 {
		t.Fatalf("receivedAmountInr = %v", got.ReceivedAmountInr)
	}
	assertEq(t, "receiptDate", got.ReceiptDate, "07-05-2026")
	assertEq(t, "remarks", got.Remarks, "Not Available")

	if len(got.Offences) != 2 {
		t.Fatalf("offences len = %d", len(got.Offences))
	}
	assertEq(t, "offence1", got.Offences[0].Offence, "Not producing DL and RC/ with out document. (LMV) Sec. 177")
	if got.Offences[0].CompoundingFeeInr != 150 {
		t.Fatalf("fee1 = %d", got.Offences[0].CompoundingFeeInr)
	}
	assertEq(t, "offence2", got.Offences[1].Offence, "A User Charges")
	if got.Offences[1].CompoundingFeeInr != 35 {
		t.Fatalf("fee2 = %d", got.Offences[1].CompoundingFeeInr)
	}

	if len(got.Images.Evidence) != 2 {
		t.Fatalf("evidence = %#v", got.Images.Evidence)
	}
	for _, u := range got.Images.Evidence {
		if !strings.Contains(u, "challans_downloaded_images") {
			t.Fatalf("unexpected evidence url %s", u)
		}
		if strings.Contains(strings.ToLower(u), "no_image") {
			t.Fatalf("placeholder leaked into evidence: %s", u)
		}
	}
	if got.Images.QR == "" || !strings.Contains(got.Images.QR, "qrcode") {
		t.Fatalf("qr = %q", got.Images.QR)
	}
	if got.Images.Map == "" || !strings.Contains(got.Images.Map, "staticmap") {
		t.Fatalf("map = %q", got.Images.Map)
	}
	if len(got.Images.All) < 6 {
		t.Fatalf("all images too few: %#v", got.Images.All)
	}
}

func assertEq(t *testing.T, name, got, want string) {
	t.Helper()
	if got != want {
		t.Fatalf("%s: got %q want %q", name, got, want)
	}
}
