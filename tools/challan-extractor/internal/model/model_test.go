package model_test

import (
	"reflect"
	"testing"

	"get1agent/tools/challan-extractor/internal/model"
)

func TestResolveURLs(t *testing.T) {
	t.Parallel()
	u1 := "https://echallan.parivahan.gov.in/report/print-page?challan_no=a"
	u2 := "https://echallan.parivahan.gov.in/report/print-page?challan_no=b"

	cases := []struct {
		name string
		req  model.Request
		want []string
	}{
		{
			name: "urls array",
			req:  model.Request{URLs: []string{u1, u2}},
			want: []string{u1, u2},
		},
		{
			name: "legacy url",
			req:  model.Request{URL: u1},
			want: []string{u1},
		},
		{
			name: "url then urls",
			req:  model.Request{URL: u1, URLs: []string{u2}},
			want: []string{u1, u2},
		},
		{
			name: "nested arguments urls",
			req:  model.Request{Arguments: &model.Request{URLs: []string{u1}}},
			want: []string{u1},
		},
		{
			name: "nested arguments url",
			req:  model.Request{Arguments: &model.Request{URL: u1}},
			want: []string{u1},
		},
		{
			name: "top level wins over arguments",
			req: model.Request{
				URLs:      []string{u2},
				Arguments: &model.Request{URLs: []string{u1}},
			},
			want: []string{u2},
		},
		{
			name: "blank entries dropped",
			req:  model.Request{URLs: []string{"", "  ", u1}},
			want: []string{u1},
		},
		{
			name: "empty",
			req:  model.Request{},
			want: nil,
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got := tc.req.ResolveURLs()
			if !reflect.DeepEqual(got, tc.want) {
				t.Fatalf("got %#v want %#v", got, tc.want)
			}
		})
	}
}
