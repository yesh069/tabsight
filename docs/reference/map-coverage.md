# Map coverage

What the bundled maps contain. The data is Natural Earth v5.1.2 (public domain), simplified for the web. This page is generated from the data by `tools/make_map_coverage.py`, and a test fails if it is out of date.

## The 30 most-used countries, checked

Each was compared with its official list of first-level regions. **Layer** is the one whose count is compared; see [maps](../guide/maps.md#layers-the-regions-people-actually-use) for what layers are.

| Country | Layer | Official | Bundled | Notes |
|---------|-------|---------:|--------:|-------|
| United States (`USA`) | `admin1` | 51 | 51 | 50 states + DC |
| India (`IND`) | `admin1` | 36 | 36 | 28 states + 8 union territories |
| Ireland (`IRL`) | `iso` | 26 | 26 | 26 counties |
| United Kingdom (`GBR`) | `nation` | 4 | 4 | 4 nations |
| Germany (`DEU`) | `admin1` | 16 | 16 | 16 states |
| France (`FRA`) | `region` | 18 | 18 | 13 metropolitan + 5 overseas regions |
| Brazil (`BRA`) | `admin1` | 27 | 27 | 26 states + federal district |
| Canada (`CAN`) | `admin1` | 13 | 13 | 10 provinces + 3 territories |
| Spain (`ESP`) | `region` | 19 | 19 | 17 communities + 2 cities |
| Italy (`ITA`) | `region` | 20 | 20 | 20 regions |
| Japan (`JPN`) | `admin1` | 47 | 47 | 47 prefectures |
| South Africa (`ZAF`) | `admin1` | 9 | 9 | 9 provinces |
| Nigeria (`NGA`) | `admin1` | 37 | 37 | 36 states + FCT |
| Switzerland (`CHE`) | `admin1` | 26 | 26 | 26 cantons |
| Sweden (`SWE`) | `admin1` | 21 | 21 | 21 counties |
| Poland (`POL`) | `admin1` | 16 | 16 | 16 voivodeships |
| Argentina (`ARG`) | `admin1` | 24 | 24 | 23 provinces + Buenos Aires city |
| South Korea (`KOR`) | `admin1` | 17 | 17 | 17 first-level divisions |
| Turkey (`TUR`) | `admin1` | 81 | 81 | 81 provinces |
| Egypt (`EGY`) | `admin1` | 27 | 27 | 27 governorates |
| China (`CHN`) | `admin1` | 34 | 32 | Hong Kong and Macau are separate countries in Natural Earth |
| Australia (`AUS`) | `iso` | 8 | 10 | plus Jervis Bay Territory and Macquarie Island |
| Mexico (`MEX`) | `admin1` | 32 | 33 | plus one small island group without a code |
| Netherlands (`NLD`) | `admin1` | 12 | 15 | plus the 3 Caribbean special municipalities |
| Indonesia (`IDN`) | `admin1` | 38 | 33 | Natural Earth predates the 2022 Papua splits |
| Russia (`RUS`) | `admin1` | 83 | 86 | includes Crimea and Sevastopol (Natural Earth's de facto view) and one small unnamed area |
| Pakistan (`PAK`) | `admin1` | 7 | 8 | still has the Tribal Areas, merged into Khyber Pakhtunkhwa in 2018 |
| Philippines (`PHL`) | `iso` | 82 | 83 | 82 provinces + Metro Manila |
| New Zealand (`NZL`) | `admin1` | 16 | 24 | plus outlying islands |
| Belgium (`BEL`) | `admin1` | 11 | 11 | 10 provinces + Brussels |

## Every country

**Regions** counts Natural Earth's level 1 (`admin1`); other layers are listed after it.

| Country | Code | Regions | Region type | Layers |
|---------|------|--------:|-------------|--------|
| Afghanistan | `AFG` | 34 | province | admin1, iso |
| Albania | `ALB` | 12 | county | admin1 |
| Algeria | `DZA` | 48 | province | admin1 |
| American Samoa | `ASM` | 5 | region | admin1 |
| Andorra | `AND` | 7 | region | admin1 |
| Angola | `AGO` | 18 | province | admin1 |
| Anguilla | `AIA` | 15 | district | admin1 |
| Antigua and Barbuda | `ATG` | 8 | parish | admin1 |
| Argentina | `ARG` | 24 | province | admin1 |
| Armenia | `ARM` | 11 | province | admin1 |
| Aruba | `ABW` | 1 | region | admin1 |
| Ashmore and Cartier Islands | `ATC` | 1 | region | admin1 |
| Australia | `AUS` | 11 | state | admin1, iso |
| Australian Indian Ocean Territories | `IOA` | 2 | province | admin1 |
| Austria | `AUT` | 9 | state | admin1 |
| Azerbaijan | `AZE` | 78 | district | admin1, iso |
| Bahrain | `BHR` | 5 | governorate | admin1 |
| Bangladesh | `BGD` | 7 | division | admin1 |
| Barbados | `BRB` | 11 | parish | admin1 |
| Belarus | `BLR` | 7 | region | admin1 |
| Belgium | `BEL` | 11 | province | admin1 |
| Belize | `BLZ` | 6 | district | admin1 |
| Benin | `BEN` | 12 | department | admin1 |
| Bermuda | `BMU` | 11 | region | admin1 |
| Bhutan | `BTN` | 20 | district | admin1 |
| Bolivia | `BOL` | 9 | department | admin1 |
| Bosnia and Herzegovina | `BIH` | 18 | canton | admin1, iso |
| Botswana | `BWA` | 15 | district | admin1 |
| Brazil | `BRA` | 27 | state | admin1 |
| British Indian Ocean Territory | `IOT` | 1 | region | admin1 |
| British Virgin Islands | `VGB` | 1 | region | admin1 |
| Brunei | `BRN` | 4 | district | admin1 |
| Bulgaria | `BGR` | 28 | province | admin1 |
| Burkina Faso | `BFA` | 45 | province | admin1 |
| Burundi | `BDI` | 17 | province | admin1 |
| Cambodia | `KHM` | 24 | province | admin1 |
| Cameroon | `CMR` | 10 | province | admin1 |
| Canada | `CAN` | 13 | province | admin1 |
| Cape Verde | `CPV` | 22 | region | admin1 |
| Cayman Islands | `CYM` | 1 | region | admin1 |
| Central African Republic | `CAF` | 17 | prefecture | admin1 |
| Chad | `TCD` | 22 | prefecture | admin1 |
| Chile | `CHL` | 16 | region | admin1 |
| China | `CHN` | 32 | province | admin1 |
| Colombia | `COL` | 34 | department | admin1, iso |
| Comoros | `COM` | 3 | region | admin1 |
| Cook Islands | `COK` | 11 | region | admin1 |
| Costa Rica | `CRI` | 7 | province | admin1 |
| Croatia | `HRV` | 21 | county | admin1, iso |
| Cuba | `CUB` | 16 | province | admin1 |
| Curaçao | `CUW` | 1 | region | admin1 |
| Cyprus | `CYP` | 5 | district | admin1 |
| Czech Republic | `CZE` | 14 | region | admin1 |
| Democratic Republic of the Congo | `COD` | 11 | province | admin1 |
| Denmark | `DNK` | 5 | region | admin1 |
| Djibouti | `DJI` | 6 | region | admin1 |
| Dominica | `DMA` | 10 | parish | admin1 |
| Dominican Republic | `DOM` | 32 | province | admin1 |
| East Timor | `TLS` | 13 | district|regencies | admin1 |
| Ecuador | `ECU` | 24 | province | admin1 |
| Egypt | `EGY` | 27 | governorate | admin1 |
| El Salvador | `SLV` | 14 | department | admin1 |
| Equatorial Guinea | `GNQ` | 7 | province | admin1 |
| Eritrea | `ERI` | 6 | region | admin1 |
| Estonia | `EST` | 15 | county | admin1 |
| Eswatini | `SWZ` | 4 | district | admin1 |
| Ethiopia | `ETH` | 11 | administrative state | admin1 |
| Falkland Islands | `FLK` | 1 | region | admin1 |
| Faroe Islands | `FRO` | 1 | region | admin1 |
| Federated States of Micronesia | `FSM` | 4 | region | admin1 |
| Fiji | `FJI` | 5 | division | admin1 |
| Finland | `FIN` | 18 | province | admin1 |
| France | `FRA` | 101 | metropolitan department | admin1, region |
| French Polynesia | `PYF` | 5 | region | admin1 |
| French Southern and Antarctic Lands | `ATF` | 4 | region | admin1 |
| Gabon | `GAB` | 9 | province | admin1 |
| Georgia | `GEO` | 12 | region | admin1 |
| Germany | `DEU` | 16 | state | admin1 |
| Ghana | `GHA` | 10 | region | admin1 |
| Greece | `GRC` | 14 | region | admin1 |
| Greenland | `GRL` | 6 | region | admin1, iso |
| Grenada | `GRD` | 7 | parish | admin1 |
| Guam | `GUM` | 1 | region | admin1 |
| Guatemala | `GTM` | 22 | department | admin1 |
| Guernsey | `GGY` | 1 | region | admin1 |
| Guinea | `GIN` | 34 | prefecture | admin1 |
| Guinea-Bissau | `GNB` | 9 | region | admin1 |
| Guyana | `GUY` | 10 | region | admin1 |
| Haiti | `HTI` | 10 | department | admin1 |
| Heard Island and McDonald Islands | `HMD` | 1 | region | admin1 |
| Honduras | `HND` | 18 | department | admin1 |
| Hong Kong | `HKG` | 18 | region | admin1 |
| Hungary | `HUN` | 43 | urban county | admin1 |
| Iceland | `ISL` | 9 | region | admin1 |
| India | `IND` | 36 | state | admin1 |
| Indonesia | `IDN` | 33 | province | admin1 |
| Iran | `IRN` | 31 | province | admin1, iso |
| Iraq | `IRQ` | 18 | province | admin1 |
| Ireland | `IRL` | 34 | county | admin1, iso |
| Isle of Man | `IMN` | 1 | region | admin1 |
| Israel | `ISR` | 6 | district | admin1 |
| Italy | `ITA` | 110 | province | admin1, region |
| Ivory Coast | `CIV` | 19 | department | admin1 |
| Jamaica | `JAM` | 14 | parish | admin1 |
| Japan | `JPN` | 47 | prefecture | admin1 |
| Jersey | `JEY` | 1 | region | admin1 |
| Jordan | `JOR` | 12 | province | admin1 |
| Kazakhstan | `KAZ` | 16 | region | admin1, iso |
| Kenya | `KEN` | 8 | province | admin1 |
| Kiribati | `KIR` | 2 | region | admin1 |
| Kosovo | `KOS` | 30 | district | admin1 |
| Kuwait | `KWT` | 6 | province | admin1 |
| Kyrgyzstan | `KGZ` | 8 | region | admin1 |
| Laos | `LAO` | 17 | province | admin1, iso |
| Latvia | `LVA` | 119 | municipality | admin1, iso |
| Lebanon | `LBN` | 6 | province | admin1 |
| Lesotho | `LSO` | 10 | district | admin1 |
| Liberia | `LBR` | 15 | county | admin1 |
| Libya | `LBY` | 22 | municipality|governarate | admin1 |
| Liechtenstein | `LIE` | 11 | region | admin1 |
| Lithuania | `LTU` | 10 | county | admin1 |
| Luxembourg | `LUX` | 3 | district | admin1 |
| Macau | `MAC` | 1 | region | admin1 |
| Madagascar | `MDG` | 22 | autonomous province | admin1, iso |
| Malawi | `MWI` | 28 | district | admin1, iso |
| Malaysia | `MYS` | 16 | state | admin1 |
| Maldives | `MDV` | 21 | atoll | admin1, iso |
| Mali | `MLI` | 9 | region | admin1 |
| Malta | `MLT` | 68 | region | admin1 |
| Marshall Islands | `MHL` | 2 | region | admin1 |
| Mauritania | `MRT` | 13 | region | admin1 |
| Mauritius | `MUS` | 16 | district | admin1, iso |
| Mexico | `MEX` | 33 | state | admin1 |
| Moldova | `MDA` | 40 | district | admin1, iso |
| Monaco | `MCO` | 1 | region | admin1 |
| Mongolia | `MNG` | 22 | province | admin1 |
| Montenegro | `MNE` | 21 | municipality | admin1 |
| Montserrat | `MSR` | 3 | parish | admin1 |
| Morocco | `MAR` | 16 | region | admin1 |
| Mozambique | `MOZ` | 11 | province | admin1, iso |
| Myanmar | `MMR` | 14 | division | admin1 |
| Namibia | `NAM` | 13 | region | admin1 |
| Nauru | `NRU` | 14 | region | admin1 |
| Nepal | `NPL` | 14 | administrative zone | admin1 |
| Netherlands | `NLD` | 15 | province | admin1 |
| New Caledonia | `NCL` | 3 | province | admin1 |
| New Zealand | `NZL` | 24 | regional council | admin1 |
| Nicaragua | `NIC` | 17 | department | admin1 |
| Niger | `NER` | 8 | department | admin1 |
| Nigeria | `NGA` | 37 | state | admin1 |
| Niue | `NIU` | 1 | region | admin1 |
| Norfolk Island | `NFK` | 1 | region | admin1 |
| North Korea | `PRK` | 11 | province | admin1 |
| North Macedonia | `MKD` | 84 | statistical region | admin1 |
| Northern Mariana Islands | `MNP` | 4 | region | admin1 |
| Norway | `NOR` | 21 | county | admin1 |
| Oman | `OMN` | 11 | region | admin1 |
| Pakistan | `PAK` | 8 | province | admin1 |
| Palau | `PLW` | 16 | region | admin1 |
| Palestine | `PSE` | 0 |  |  |
| Panama | `PAN` | 12 | province | admin1 |
| Papua New Guinea | `PNG` | 20 | province | admin1 |
| Paraguay | `PRY` | 18 | department | admin1 |
| Peru | `PER` | 26 | department | admin1, iso |
| Philippines | `PHL` | 118 | province | admin1, iso, region |
| Pitcairn Islands | `PCN` | 1 | region | admin1 |
| Poland | `POL` | 16 | voivodeship|province | admin1 |
| Portugal | `PRT` | 20 | district | admin1 |
| Puerto Rico | `PRI` | 1 | region | admin1 |
| Qatar | `QAT` | 7 | municipality | admin1 |
| Republic of the Congo | `COG` | 12 | region | admin1 |
| Romania | `ROU` | 42 | county | admin1 |
| Russia | `RUS` | 86 | region | admin1 |
| Rwanda | `RWA` | 5 | province | admin1 |
| Saint Barthélemy | `BLM` | 1 | region | admin1 |
| Saint Helena | `SHN` | 3 | region | admin1 |
| Saint Kitts and Nevis | `KNA` | 14 | parish | admin1 |
| Saint Lucia | `LCA` | 11 | quarter | admin1 |
| Saint Martin | `MAF` | 1 | region | admin1 |
| Saint Pierre and Miquelon | `SPM` | 2 | commune | admin1 |
| Saint Vincent and the Grenadines | `VCT` | 6 | parish | admin1 |
| Samoa | `WSM` | 11 | region | admin1 |
| San Marino | `SMR` | 9 | region | admin1 |
| Saudi Arabia | `SAU` | 13 | region | admin1 |
| Senegal | `SEN` | 14 | region | admin1 |
| Serbia | `SRB` | 25 | district | admin1 |
| Seychelles | `SYC` | 26 | region | admin1 |
| Siachen Glacier | `KAS` | 1 | region | admin1 |
| Sierra Leone | `SLE` | 4 | province | admin1 |
| Singapore | `SGP` | 5 | region | admin1 |
| Sint Maarten | `SXM` | 1 | region | admin1 |
| Slovakia | `SVK` | 8 | region | admin1 |
| Slovenia | `SVN` | 193 | commune|municipality | admin1, iso |
| Solomon Islands | `SLB` | 10 | province | admin1, iso |
| Somalia | `SOM` | 13 | region | admin1 |
| Somaliland | `SOL` | 1 | region | admin1 |
| South Africa | `ZAF` | 9 | province | admin1 |
| South Georgia and the South Sandwich Islands | `SGS` | 1 | region | admin1 |
| South Korea | `KOR` | 17 | metropolitan city | admin1 |
| South Sudan | `SSD` | 0 |  |  |
| Spain | `ESP` | 52 | autonomous community | admin1, region |
| Sri Lanka | `LKA` | 25 | district | admin1 |
| Sudan | `SDN` | 17 | state | admin1, iso |
| Suriname | `SUR` | 10 | district | admin1 |
| Sweden | `SWE` | 21 | county | admin1 |
| Switzerland | `CHE` | 26 | canton | admin1 |
| Syria | `SYR` | 15 | province | admin1 |
| São Tomé and Príncipe | `STP` | 2 | region | admin1 |
| Taiwan | `TWN` | 21 | county | admin1 |
| Tajikistan | `TJK` | 5 | region | admin1 |
| Tanzania | `TZA` | 30 | region | admin1 |
| Thailand | `THA` | 77 | province | admin1 |
| The Bahamas | `BHS` | 30 | district | admin1 |
| The Gambia | `GMB` | 6 | division | admin1 |
| Togo | `TGO` | 5 | region | admin1 |
| Tonga | `TON` | 5 | region | admin1 |
| Trinidad and Tobago | `TTO` | 16 | region | admin1 |
| Tunisia | `TUN` | 23 | governorate | admin1 |
| Turkey | `TUR` | 81 | province | admin1 |
| Turkish Republic of Northern Cyprus | `CYN` | 1 | region | admin1 |
| Turkmenistan | `TKM` | 5 | province | admin1 |
| Turks and Caicos Islands | `TCA` | 6 | region | admin1 |
| Tuvalu | `TUV` | 1 | region | admin1 |
| Uganda | `UGA` | 112 | district | admin1, iso |
| Ukraine | `UKR` | 25 | region | admin1 |
| United Arab Emirates | `ARE` | 9 | emirate | admin1 |
| United Kingdom | `GBR` | 232 | unitary authority | admin1, nation, region |
| United States | `USA` | 51 | state | admin1 |
| United States Virgin Islands | `VIR` | 3 | region | admin1 |
| Uruguay | `URY` | 19 | department | admin1 |
| Uzbekistan | `UZB` | 14 | region | admin1 |
| Vanuatu | `VUT` | 6 | province | admin1 |
| Vatican City | `VAT` | 1 | region | admin1 |
| Venezuela | `VEN` | 26 | state | admin1 |
| Vietnam | `VNM` | 63 | province | admin1 |
| Wallis and Futuna | `WLF` | 3 | region | admin1 |
| Western Sahara | `ESH` | 0 |  |  |
| Yemen | `YEM` | 21 | governorate | admin1 |
| Zambia | `ZMB` | 10 | province | admin1 |
| Zimbabwe | `ZWE` | 10 | province | admin1 |
| Åland | `ALA` | 0 |  |  |
